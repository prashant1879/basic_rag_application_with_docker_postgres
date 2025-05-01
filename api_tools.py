import sys
import asyncio

# Ensure Windows compatibility for asyncio with psycopg
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import os
from dotenv import load_dotenv
import chromadb

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langchain_core.messages import HumanMessage, AIMessage
from logger import logger
from langchain.prompts import PromptTemplate
from langchain_chroma import Chroma
from chromadb.config import Settings as ChromaDbSettings
from langchain_openai import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    Docx2txtLoader as Docx2txtLoader,
    UnstructuredMarkdownLoader,
)
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from typing import TypedDict
from langgraph.graph.message import add_messages
from typing_extensions import Annotated
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver, AsyncConnectionPool

    
load_dotenv()

vector_store = None

def markdown_to_plain_text(markdown_text: str) -> str:
    """
    Converts Markdown-formatted text into plain text by removing all formatting such as headings, bold, italics, code, and bullet points.

    Args:
        markdown_text (str): A string containing text formatted in Markdown.

    Returns:
        str: The input text converted to plain, unformatted text.
    """
    import re

    # Remove headings (e.g., # Heading)
    markdown_text = re.sub(r'^#+\s*(.*)', r'\1', markdown_text, flags=re.MULTILINE)

    # Remove bullet points (- item or * item)
    markdown_text = re.sub(r'^\s*[-*]\s+', '', markdown_text, flags=re.MULTILINE)

    # Remove bold (**text**)
    markdown_text = re.sub(r'\*\*(.*?)\*\*', r'\1', markdown_text)

    # Remove italics (*text* or _text_)
    markdown_text = re.sub(r'(?<!\*)\*(?!\*)(.*?)\*(?!\*)', r'\1', markdown_text)  # *italic*
    markdown_text = re.sub(r'_(.*?)_', r'\1', markdown_text)  # _italic_

    # Remove inline code
    markdown_text = re.sub(r'`{1,3}(.*?)`{1,3}', r'\1', markdown_text)

    # Normalize multiple newlines
    markdown_text = re.sub(r'\n{3,}', '\n\n', markdown_text)

    return markdown_text.strip()

# --------------------------------------------------------------------------------
# Create vector Store ------------------------------------------------------------
# --------------------------------------------------------------------------------
class VectorStore:
    """
    This class has static methods for initialising and working with the self.
    """
    _initialized: bool = False
    _CHUNK_SIZE: str = ""
    _CHUNK_OVERLAP: str = ""
    _DB_PATH: str = ""
    _DOCUMENT_PATH: str = ""
    _DB_COLLECTION_NAME: str = ""
    _CHATSESSION_DATABASE_PATH: str = ""
    _OPENAI_API_KEY: str = ""
    _chroma_client: chromadb.PersistentClient = None
    _chroma: Chroma = None
    
    def __init__(self):
        self._initialized = False
        self.legal_file_extensions = ['.md']  # Define your legal extensions here
        
    async def init(self):
        if not self._initialized:
            try:
                # Load environment variables
                self._DB_COLLECTION_NAME = os.environ['DB_COLLECTION_NAME']
                self._DB_PATH = os.environ['DB_PATH']
                self._OPENAI_API_KEY = os.environ['OPENAI_API_KEY']
                self._CHUNK_SIZE = int(os.environ['CHUNK_SIZE'])
                self._CHUNK_OVERLAP = int(os.environ['CHUNK_OVERLAP'])
                self._DOCUMENT_PATH = os.environ['DOCUMENT_PATH']
                self._CHATSESSION_DATABASE_PATH = os.environ['CHATSESSION_DATABASE_PATH']

                # Initialize ChromaDB client
                self._chroma_client = chromadb.PersistentClient(
                    path=self._DB_PATH,
                    settings=ChromaDbSettings(allow_reset=True, anonymized_telemetry=False)
                )

                chroma_collection = self._chroma_client.get_or_create_collection(self._DB_COLLECTION_NAME)

                self._chroma = Chroma(
                    client=self._chroma_client,
                    collection_name=self._DB_COLLECTION_NAME,
                    embedding_function=OpenAIEmbeddings(openai_api_key=self._OPENAI_API_KEY),
                )

                collection = self._chroma.get()
                if len(collection.get('documents', [])) == 0:
                    logger.info("Regenerating vector store...")

                    docs_path = self._DOCUMENT_PATH
                    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
                        chunk_size=self._CHUNK_SIZE,
                        chunk_overlap=self._CHUNK_OVERLAP
                    )

                    all_documents = []

                    for filename in os.listdir(docs_path):
                        if filename.lower().endswith(tuple(self.legal_file_extensions)):
                            full_file_path = os.path.join(docs_path, filename)

                            try:
                                document = UnstructuredMarkdownLoader(full_file_path, mode="single").load()
                                document[0].metadata.update(
                                    {'fileName': filename}
                                )
                                
                                split_docs = text_splitter.split_documents(document)
                                
                                all_documents.extend(split_docs)
                            except Exception as e:
                                logger.info(f"Error processing file {filename}: {e}")

                    try:
                        if all_documents:
                            logger.info("Adding docs to the vector store...")
                            self._chroma.add_documents(documents=all_documents)
                            logger.info(f"Added {len(all_documents)} documents to vector store.")
                        else:
                            logger.info("No documents found to add to vector store.")
                    except Exception as e:
                        logger.info(f"Failed to add documents to Chroma: {e}")
                
                self._initialized = True
                logger.info("Initialization complete.")
            except Exception as e:
                logger.info(f"Initialization failed: {e}")
                return False

    async def search_query(self, query: str):
        try:
            fileNameCollection = []
            for singleFileName in os.listdir(self._DOCUMENT_PATH):
                fileNameCollection.append({'fileName': singleFileName})

            # Get just the list of filenames
            file_names = [f['fileName'] for f in fileNameCollection]

            # ChromaDB expects a filter dictionary. If you want to match any of the filenames:
            collection_filter = {"fileName": {"$in": file_names}}

            response = self._chroma.similarity_search_with_score(query=query, filter=collection_filter, k=2)
                                    
            return response
        except Exception as e:
            logger.info(f"Search failed: {e}")
            return []
        
async def get_vector_store() -> VectorStore:
    global vector_store
        
    if vector_store is None:
        vector_store= VectorStore()
        await vector_store.init()
        return vector_store
    else:
        return vector_store

# --------------------------------------------------------------------------------
# Create Prompts
# --------------------------------------------------------------------------------

def get_prompt():
    return PromptTemplate.from_template(
        """You are a helpful assistant for a tourism chatbot. Use ONLY the context provided below to answer the user's question.

        If the answer to the question is **not present** in the context, then provide contact information from vector db.

        ---
        Context:
        {context}
        ---

        Question:
        {question}

        Answer:
        Format your response clearly and professionally, using only the information from the context."""
    )

    
# --------------------------------------------------------------------------------
# Building the graph -------------------------------------------------------------
# --------------------------------------------------------------------------------
class AICompanionState(TypedDict):
    """State class for the AI Companion graph_builder.
    Extends MessagesState to track conversation history and maintains the last message received.
    Attributes:
        LangChain message type (HumanMessage, AIMessage, etc.)
    """
    messages: Annotated[list , add_messages]
    
def create_agent(llm, agent):
    async def node_handler(state):
        try:
            logger.info("Current state messages:")
            for msg in state["messages"]:
                logger.info(f"{type(msg)}: {msg.content}")

            user_message = next((msg.content for msg in reversed(state["messages"]) if isinstance(msg, HumanMessage)),"")

            if not user_message:
                logger.warning("No HumanMessage found.")
                return {"messages": state["messages"]}

            # Vector store call (assumed to return List[Tuple[Document, float]])
            results = await vector_store.search_query(user_message)

            if not results:
                return {
                    "messages": state["messages"] + [AIMessage(content="No relevant data found.")]
                }

            final_result: str = ''
            for result in results:
                # result is a tuple of Document and score
                document, score = result
                final_result += ( f"\r\n\r\n### {document.metadata['fileName'].lower()} INFORMATION:\r\n" + document.page_content )

            if not final_result:
                text: str = "No suitable results for the given query. Try to extend or redefine your query."

            else:
                text: str = "The search resulted with following text: \r\n" + final_result

            # Here we append the current message and context before sending it to the model.
            conversation_context = "\r\n".join([msg.content for msg in state["messages"] if isinstance(msg, HumanMessage)])
            
            # Run OpenAI only to format the DB content
            response = await agent.ainvoke({
                "context": conversation_context + "\r\n" + text,  # Include conversation history
                "question": user_message
            })
            
            return {
                "messages": state["messages"] + [AIMessage(content=response.content)]
            }

        except Exception as e:
            logger.exception("Exception in node_handler:")
            return {"messages": state.get("messages", [])}

    return node_handler



def create_workflow_graph():
    logger.info("Starting to build graph_builder graph...")

    llmModel = "gpt-4o-mini"
    temperature = 0.2
    streaming = True

    # Prepare LLM
    llm = ChatOpenAI(
        model=llmModel,
        temperature=temperature,
        streaming=streaming
    )

    prompt = get_prompt()
    agent = prompt | llm

    create_agent_node = create_agent(llm=llm, agent=agent)

    graph_builder = StateGraph(AICompanionState)
    graph_builder.add_node("conversation_node", create_agent_node)
    graph_builder.add_edge(START, "conversation_node")
    graph_builder.add_edge("conversation_node", END)

    logger.info("Graph built successfully.")
    return graph_builder

async def create_chatbot_service():
    """
    Initializes and sets up the necessary components for a chatbot service, including:
    - An asynchronous database connection pool.
    - An asynchronous checkpointer for saving data.
    - A compiled graph_builder for the chatbot's operation.

    This function performs the following setup:
    1. Initializes an `AsyncConnectionPool` for handling database connections asynchronously.
    2. Sets up the `AsyncPostgresSaver` checkpointer to handle saving data asynchronously.
    3. Prepares the chatbot graph_builder by calling the `create_workflow_graph` function.

    Returns:
        tuple: A tuple containing the following components:
            - `checkpointer`: The initialized async checkpointer (`AsyncPostgresSaver`).
            - `graph_builder`: The compiled chatbot graph_builder.
            - `pool`: The async database connection pool (`AsyncConnectionPool`).

    Raises:
        Exception: If any error occurs during the setup process, the function raises an exception.
        - In case of an error, any opened resources (e.g., the connection pool) will be properly closed.
    """

    connection_kwargs = {
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
    }

    pool = None
    try:
        pool = AsyncConnectionPool(
            conninfo=os.environ['CHATSESSION_DATABASE_PATH'],
            max_size=20,
            open=False,
            timeout=5,
            kwargs=connection_kwargs
        )
        await pool.open(wait=True, timeout=10)

        checkpointer = AsyncPostgresSaver(conn=pool)
        await checkpointer.setup()

        return checkpointer, pool

    except Exception as e:
        logger.error(f"Error during setup: {e}")
        if pool:
            await pool.close()
        raise
    
async def init_chatbot():
    logger.info("Chatbot init...")
    global graph_builder
    global checkpointer
    global pool    
    graph_builder = create_workflow_graph()
    checkpointer, pool = await create_chatbot_service()

# --------------------------------------------------------------------------------
# Invoke model for API -----------------------------------------------------------
# --------------------------------------------------------------------------------
async def invoke_model(message: str, phone_number: str):
    logger.info(f"Invoking model for phone_number: {phone_number}")


    try:        
        graph = graph_builder.compile(checkpointer=checkpointer)
        await graph.ainvoke(
            {"messages": [HumanMessage(content=message)]},
            {"configurable": {"thread_id": phone_number}},
        )

        state = await graph.aget_state(config={"configurable": {"thread_id": phone_number}})
        response = state.values["messages"][-1].content
        return markdown_to_plain_text(response)

    except Exception as e:
        logger.error(f'Error during chat: {e}')
        logger.critical(f"Chat error: {e}")
        return "An error occurred during the conversation."

# --------------------------------------------------------------------------------
# CHAT API -----------------------------------------------------------------------
# --------------------------------------------------------------------------------
async def chat_start_api(request):
    content = request.question
    phone_number = request.phone_number
    try:
        logger.info("Chat Starting...")
        message = await invoke_model(content, phone_number, graph_builder)
        logger.info("Chat End...")
        return {"phone_number": phone_number, "message":message}
    except Exception as e:
        logger.info(f"Error chat_start_api {e}")
       