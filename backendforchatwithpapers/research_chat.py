import os
import hashlib
from urllib.parse import urlparse
from typing import Optional, List
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.ai.formrecognizer import DocumentAnalysisClient
from openai import AzureOpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class ResearchPaperAssistant:
    def __init__(self):
        """Initialize Azure services with optimized configuration"""
        # Service clients initialization
        self.search_client = SearchClient(
            endpoint=os.getenv("AZURE_SEARCH_ENDPOINT"),
            index_name="paper-videos",
            credential=AzureKeyCredential(os.getenv("AZURE_SEARCH_KEY")))
        
        self.document_analysis_client = DocumentAnalysisClient(
            endpoint=os.getenv("AZURE_DOC_INTEL_ENDPOINT"),
            credential=AzureKeyCredential(os.getenv("AZURE_DOC_INTEL_KEY")))
        
        self.openai_client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version="2024-05-01-preview")
        
        # Reduced configuration constants
        self.MAX_CONTENT_LENGTH = 4000  # characters (~1000 tokens)
        self.SUMMARY_LENGTH = 2000      # characters (~500 tokens)
        self.CHUNK_OVERLAP = 200        # characters overlap between chunks
        self.EMBEDDING_MODEL = "text-embedding-3-large"
        self.CHAT_MODEL = "gpt-4"   # Ensure correct deployment name
        self.POLLING_INTERVAL = 30      # seconds for Document Intelligence
        self.MAX_ANSWER_TOKENS = 300    # for concise answers

    def _validate_pdf_url(self, url: str) -> bool:
        """Validate PDF URL format and extension"""
        try:
            parsed = urlparse(url)
            return (all([parsed.scheme, parsed.netloc]) and 
                    (url.lower().endswith('.pdf') or 'pdf' in parsed.path.lower()))
        except Exception:
            return False

    def _generate_document_id(self, pdf_url: str, title: str) -> str:
        """Generate consistent document ID from URL and title"""
        return hashlib.sha256(f"{pdf_url}-{title}".encode()).hexdigest()

    def _chunk_content(self, content: str) -> List[str]:
        """
        Efficient content chunking with strict length control
        """
        # Split into sentences or smaller chunks
        sentences = [s.strip() for s in content.replace('\n', ' ').split('.') if s.strip()]
        chunks = []
        current_chunk = []
        current_length = 0

        for sentence in sentences:
            sentence_length = len(sentence)
            if current_length + sentence_length > self.MAX_CONTENT_LENGTH:
                chunks.append(". ".join(current_chunk) + ".")
                # Reset with overlap
                current_chunk = current_chunk[-1:] if current_chunk else []
                current_length = len(current_chunk[0]) if current_chunk else 0
            
            current_chunk.append(sentence)
            current_length += sentence_length + 2  # +2 for ". "

        if current_chunk:
            chunks.append(". ".join(current_chunk) + ".")

        return chunks[:3]  # Limit to first 3 chunks

    def _get_text_embedding(self, text: str) -> Optional[List[float]]:
        """Safe embedding generation with strict length handling"""
        try:
            # Ensure text is well under token limit
            truncated_text = text[:self.MAX_CONTENT_LENGTH]
            response = self.openai_client.embeddings.create(
                input=truncated_text,
                model=self.EMBEDDING_MODEL)
            return response.data[0].embedding
        except Exception as e:
            print(f"Embedding generation failed: {str(e)}")
            return None

    def process_paper(self, pdf_url: str, title: str) -> Optional[str]:
        """
        Optimized paper processing pipeline with stricter limits
        """
        if not self._validate_pdf_url(pdf_url):
            print(f"Invalid PDF URL: {pdf_url}")
            return None

        doc_id = self._generate_document_id(pdf_url, title)

        # Check for existing document to avoid reprocessing
        try:
            existing_doc = self.search_client.get_document(key=doc_id)
            print(f"Document already indexed: {existing_doc['title']}")
            return doc_id
        except Exception:
            pass  # Document doesn't exist, proceed with processing

        try:
            # Step 1: Extract text from PDF
            poller = self.document_analysis_client.begin_analyze_document_from_url(
                "prebuilt-read",
                pdf_url,
                polling_interval=self.POLLING_INTERVAL)
            result = poller.result()
            full_text = " ".join(p.content for p in result.paragraphs)

            if not full_text.strip():
                print("No text content extracted from PDF")
                return None

            # Step 2: Chunk content (using first chunk for embedding)
            chunks = self._chunk_content(full_text)
            if not chunks:
                print("Failed to chunk document content")
                return None

            # Step 3: Generate embedding from first chunk
            embedding = self._get_text_embedding(chunks[0])
            if not embedding:
                print("Failed to generate document embedding")
                return None

            # Step 4: Prepare document for indexing
            document = {
                "id": doc_id,
                "title": title,
                "content": chunks[0][:self.MAX_CONTENT_LENGTH],
                "content_vector": embedding,
                "url": pdf_url  # No full_text_length or chunk_count
            }

            # Step 5: Index document
            self.search_client.upload_documents(documents=[document])
            print(f"Successfully indexed paper: {title}")
            return doc_id

        except Exception as e:
            print(f"Paper processing failed: {str(e)}")
            return None

    def ask_question(self, question: str, doc_id: str) -> Optional[str]:
        """
        Efficient question answering with reduced context
        """
        try:
            # Verify document exists
            document = self.search_client.get_document(key=doc_id)

            # Generate question embedding
            question_embedding = self._get_text_embedding(question)
            if not question_embedding:
                print("Failed to generate question embedding")
                return None

            # Hybrid search (combining text and vector search)
            search_results = self.search_client.search(
                search_text=question,
                vector_queries=[{
                    "fields": "content_vector",
                    "kind": "vector",
                    "vector": question_embedding,
                    "k": 2  # Reduced number of results
                }],
                select=["content", "title"],
                top=2  # Reduced number of top results
            )

            # Build focused context from search results
            context_parts = []
            for i, hit in enumerate(search_results):
                excerpt = hit['content'][:500]  # Reduced excerpt length
                context_parts.append(f"[Passage {i+1}]: {excerpt}")
            
            context = "\n".join(context_parts) if context_parts else "No relevant passages found"

            # Generate concise answer
            response = self.openai_client.chat.completions.create(
                model=self.CHAT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a research paper assistant. Answer the question "
                            "concisely based on the provided context. Be precise and brief.\n"
                            f"Paper Title: {document['title']}"
                        )
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Question: {question}\n"
                            f"Context:\n{context}\n"
                            "Provide a very concise answer referencing the paper."
                        )
                    }
                ],
                temperature=0.3,
                max_tokens=self.MAX_ANSWER_TOKENS
            )
            return response.choices[0].message.content

        except Exception as e:
            print(f"Question answering failed: {str(e)}")
            return None

def main():
    assistant = ResearchPaperAssistant()
    
    # Example paper processing
    papers = [
        ("http://arxiv.org/pdf/2105.14199v1", "Impact of Public and Private Investments on Economic Growth of Developing Countries"),
    ]
    
    for pdf_url, title in papers:
        print(f"\nProcessing: {title}")
        doc_id = assistant.process_paper(pdf_url, title)
        
        if not doc_id:
            print("Failed to process paper, moving to next...")
            continue
        
        # Interactive Q&A session
        while True:
            question = input("\nAsk a question about the paper (or type 'next'/'exit'): ").strip()
            
            if question.lower() in ('exit', 'quit'):
                return
            
            if question.lower() == 'next':
                break
            
            if not question:
                continue
            
            answer = assistant.ask_question(question, doc_id)
            
            if answer:
                print(f"\nANSWER: {answer}\n(Source: {pdf_url})")
            else:
                print("Sorry, I couldn't generate an answer for that question.")

if __name__ == "__main__":
    main()
