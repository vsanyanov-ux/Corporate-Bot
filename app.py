import streamlit as st
from langchain_ollama import ChatOllama
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_classic.chains import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
import langfuse
from langfuse import Langfuse
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
CHROMA_PATH = "chroma_db"
LLM_MODEL = "qwen2.5:3b"
EMBEDDING_MODEL = "nomic-embed-text"

st.set_page_config(page_title="Корпоративный Бот", page_icon="🤖", layout="centered")

# Initialize LLM and Embeddings
# @st.cache_resource
def load_resources():
    embeddings = OllamaEmbeddings(model=EMBEDDING_MODEL)
    vectorstore = Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)
    llm = ChatOllama(model=LLM_MODEL, temperature=0.3)
    
    # Langfuse Client
    langfuse = Langfuse()
    return vectorstore, llm, langfuse

vectorstore, llm, langfuse = load_resources()

# Setup RAG Prompt
system_prompt = (
    "Ты — полезный корпоративный помощник. Используй предоставленный контекст, чтобы отвечать на вопросы. "
    "Если ответа нет в контексте, вежливо скажи, что не знаешь. "
    "Отвечай на языке запроса пользователя (обычно русский). "
    "\n\n"
    "{context}"
)

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system_prompt),
        ("human", "{input}"),
    ]
)

# Create RAG Chain
question_answer_chain = create_stuff_documents_chain(llm, prompt)
rag_chain = create_retrieval_chain(vectorstore.as_retriever(search_kwargs={"k": 10}), question_answer_chain)

# UI Implementation
st.title("🤖 Корпоративный Помощник")
st.markdown("---")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
if user_input := st.chat_input("Спросите что-нибудь о документах..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Думаю..."):
            # Create Langfuse trace
            trace = langfuse.trace(name="Chat Message", input=user_input)
            generation = trace.generation(name="RAG Answer", input=user_input)
            
            # Prepare streaming container
            response_placeholder = st.empty()
            full_answer = ""
            
            # Use stream()
            sources = set()
            for chunk in rag_chain.stream({"input": user_input}):
                if "context" in chunk:
                    for doc in chunk["context"]:
                        sources.add(os.path.basename(doc.metadata.get("source", "Unknown")))
                
                if "answer" in chunk:
                    full_answer += chunk["answer"]
                    response_placeholder.markdown(full_answer + "▌")
            
            # Finalize the answer
            response_placeholder.markdown(full_answer)
            
            # End Langfuse generation
            generation.end(output=full_answer, metadata={"sources": list(sources)})
            
            # Show sources for transparency
            if sources:
                st.caption(f"📚 Источники: {', '.join(sources)}")
            
            st.session_state.messages.append({"role": "assistant", "content": full_answer})

# Sidebar info
with st.sidebar:
    st.header("О системе")
    st.write(f"**Модель:** {LLM_MODEL}")
    st.write(f"**Эмбеддинги:** {EMBEDDING_MODEL}")
    st.write("---")
    st.info("Бот анализирует документы из папки `data/` и отвечает на вопросы.")
