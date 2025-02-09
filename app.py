import streamlit as st
from langchain.chains import create_history_aware_retriever,create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
#from langchain_chroma import Chroma
from langchain_community.vectorstores import FAISS
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.prompts import MessagesPlaceholder,ChatPromptTemplate
from langchain_groq import ChatGroq
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
import os

from dotenv import load_dotenv
load_dotenv()

os.environ['HF_TOKEN']=os.getenv("HF_TOKEN")
embeddings=HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

##Set Up Streamlit APP
st.title("Conversational RAG With PDF uploads and Chat History")
st.write("Upload Pdf and ask about the content")

groq_api_key=os.getenv("GROQ_API_KEY")

llm=ChatGroq(groq_api_key=groq_api_key,model="Gemma2-9b-It")
session_id=st.text_input("Session ID",value="default_session")


##Manage Chat History
if 'store' not in st.session_state:
    st.session_state.store={}

uploaded_files=st.file_uploader("Choose a PDF file",type="pdf",accept_multiple_files=True)
if uploaded_files:
    documents=[]
    for uploaded_file in uploaded_files:
        temppdf=f"./temp.pdf"
        with open(temppdf,"wb") as file:
            file.write(uploaded_file.getvalue())
            file_name=uploaded_file.name
        
        loader=PyPDFLoader(temppdf)
        docs=loader.load()
        documents.extend(docs)

    #Split and create embeddings for the documents
    text_splitter=RecursiveCharacterTextSplitter(chunk_size=5000,chunk_overlap=200)
    split=text_splitter.split_documents(documents)
    vectorStore=FAISS.from_documents(documents=split,embedding=embeddings)
    retriever=vectorStore.as_retriever()


    contextualize_q_system_prompt=(
        "Given a chat history and the latest user question"
        "which might refernce context in the chat history"
        "formulate a standalone question which can be understood"
        "without the chat history.Do not answer the question,"
        "just reformulate it if needed and otherwise return it as is"
    )

    contextualize_q_prompt=ChatPromptTemplate.from_messages(
        [
            ("system",contextualize_q_system_prompt),
            MessagesPlaceholder("chat_history"),
            ("human","{input}")
        ]
    )

    history_aware=create_history_aware_retriever(llm,retriever,contextualize_q_prompt)

    ## Answer question
    system_prompt=(
    "You are an assistant for question-answering tasks"
    "Use the folowing pieces of retrieved context to answer"
    "the question.If you don't know the answer,say taht you"
    "don't know.Use three sentences maximum and keep the"
    "answer concise"
    "\n\n"
    "{context}"
    )

    qa_prompt=ChatPromptTemplate.from_messages(
        [
            ("system",system_prompt),
            MessagesPlaceholder("chat_history"),
            ("human","{input}")
        ]
    )

    question_answer_chain=create_stuff_documents_chain(llm,qa_prompt)
    rag_chain=create_retrieval_chain(history_aware,question_answer_chain)

    def get_session_history(session_id:str)->BaseChatMessageHistory:
        if session_id not in st.session_state.store:
            st.session_state.store[session_id]=ChatMessageHistory()
        return st.session_state.store[session_id]
    
    conversational_rag_chain=RunnableWithMessageHistory(
        rag_chain,
        get_session_history,
        input_messages_key="input",
        history_messages_key="chat_history",
        output_messages_key="answer"
    )

    user_input=st.text_input("Your questions")
    if user_input:
        session_history=get_session_history(session_id)
        response=conversational_rag_chain.invoke(
            {"input":user_input},
            config={
                "configurable":{"session_id":session_id}
            }
        )

        st.write(st.session_state.store)
        st.write("Assistant:",response['answer'])
        st.write("Chat History:",session_history.messages)
