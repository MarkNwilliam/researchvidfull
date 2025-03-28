import os
import hashlib
import re
import time
from typing import Dict, Optional, List  # Added this import
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.ai.formrecognizer import DocumentAnalysisClient
from openai import AzureOpenAI
from dotenv import load_dotenv
import requests
from functools import lru_cache
from urllib.parse import urlparse
import json

load_dotenv()

class ChatWithPaper:
    def __init__(self):
        """Initialize with Azure services"""
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

        # Configuration
        self.MAX_CONTENT_LENGTH = 4000
        self.CHAT_MODEL = "gpt-4"
        self.EMBEDDING_MODEL = "text-embedding-3-large"

    def chat_with_paper(self, pdf_url: str, title: str, question: str) -> Dict:
        """
        One-stop method to:
        1. Check if paper exists
        2. Index if needed
        3. Answer question
        """
        # Validate inputs
        if not all([pdf_url, title, question]):
            return {"error": "Missing pdf_url, title, or question"}
        
        if not self._validate_pdf(pdf_url):
            return {"error": "Invalid PDF URL"}

        # Generate document ID
        doc_id = self._generate_doc_id(pdf_url, title)

        # Check if paper exists, process if not
        if not self._paper_exists(doc_id):
            process_result = self._process_paper(pdf_url, title, doc_id)
            if "error" in process_result:
                return process_result

        # Answer the question
        return self._answer_question(doc_id, question, title)

    def _process_paper(self, pdf_url: str, title: str, doc_id: str) -> Dict:
        """Process and index a paper"""
        try:
            # Extract text
            text = self._extract_text(pdf_url)
            if not text:
                return {"error": "No text extracted from PDF"}

            # Create embedding
            embedding = self._get_embedding(text[:self.MAX_CONTENT_LENGTH])
            if not embedding:
                return {"error": "Failed to generate embedding"}

            # Index document
            self.search_client.upload_documents(documents=[{
                "id": doc_id,
                "title": title,
                "content": text[:self.MAX_CONTENT_LENGTH],
                "content_vector": embedding,
                "url": pdf_url
            }])
            
            return {"status": "processed"}
        except Exception as e:
            return {"error": f"Processing failed: {str(e)}"}
    
    def generate_practice_questions(
        self, 
        pdf_url: str, 
        title: str, 
        num_questions: int = 5, 
        difficulty: str = "medium",
        question_type: str = "mixed",
        description: str = ""
    ) -> Dict:
        """
        Generate multiple practice questions about the paper with customization options
        
        Args:
            pdf_url: URL of the PDF
            title: Title of the paper
            num_questions: Number of questions to generate (default 5)
            difficulty: Difficulty level (easy, medium, hard)
            question_type: Type of questions ('conceptual', 'technical', 'application', 'mixed')
            description: User's description of what kind of questions they want
        """
        # Validate inputs
        if not all([pdf_url, title]):
            return {"error": "Missing pdf_url or title"}
        
        if not self._validate_pdf(pdf_url):
            return {"error": "Invalid PDF URL"}

        try:
            # Extract text from PDF
            text = self._extract_text(pdf_url)
            if not text:
                return {"error": "No text content extracted from PDF"}

            # Generate document ID (for caching)
            doc_id = self._generate_doc_id(pdf_url, title)
            
            # Create prompt based on user preferences
            type_instructions = {
                'conceptual': "Focus on theoretical concepts and definitions.",
                'technical': "Focus on methodologies, techniques, and technical details.",
                'application': "Focus on practical applications and implications.",
                'mixed': "Include a mix of conceptual, technical, and application questions."
            }.get(question_type, "Include a mix of question types.")
            
            description_text = f"\nAdditional instructions: {description}" if description else ""
            
            prompt = f"""
            Generate {num_questions} {difficulty}-level multiple choice questions about this research paper titled "{title}".
            {type_instructions}{description_text}
            
            For each question, provide:
            - A clear, specific question about the paper's content
            - 4 plausible multiple choice options (labeled a-d)
            - The correct answer (a-d)
            - A detailed explanation that includes:
            * Why the correct answer is right (with specific references to the paper)
            * Why each incorrect option is wrong
            * Any relevant context from the paper that helps understand the answer
            
            Paper content (first 8000 characters):
            {text[:8000]}
            
            Return the questions in JSON format with this exact structure:
            {{
                "questions": [
                    {{
                        "question": "...",
                        "options": {{
                            "a": "...",
                            "b": "...",
                            "c": "...",
                            "d": "..."
                        }},
                        "correct_answer": "a",
                        "explanation": {{
                            "correct": "Explanation of why this is right...",
                            "incorrect": {{
                                "a": "Why this option is wrong...",
                                "b": "Why this option is wrong...",
                                "c": "Why this option is wrong..."
                            }},
                            "additional_context": "Any relevant context from the paper..."
                        }}
                    }}
                ],
                "metadata": {{
                    "paper_title": "{title}",
                    "generated_at": "{time.ctime()}",
                    "difficulty": "{difficulty}",
                    "question_type": "{question_type}",
                    "user_description": "{description}"
                }}
            }}
            """

            # Call OpenAI API
            response = self.openai_client.chat.completions.create(
                model=self.CHAT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                response_format={"type": "json_object"},
                max_tokens=2000
            )
            
            questions_data = json.loads(response.choices[0].message.content)
            
            if not isinstance(questions_data.get("questions"), list):
                return {"error": "Invalid question format generated"}
                
            self._cache_questions(doc_id, questions_data)
            
            return questions_data
            
        except Exception as e:
            return {"error": f"Failed to generate questions: {str(e)}"}
    
    def _cache_questions(self, doc_id: str, questions_data: Dict):
        """Optional: Cache generated questions in Azure Search"""
        try:
            # Add document ID to the metadata
            questions_data["metadata"]["doc_id"] = doc_id
            
            # Index the questions
            self.search_client.upload_documents(documents=[{
                "id": f"{doc_id}-questions",
                "type": "practice_questions",
                "content": json.dumps(questions_data),
                "content_vector": self._get_embedding(
                    f"Practice questions for document {doc_id}"
                )
            }])
        except Exception as e:
            print(f"Warning: Failed to cache questions: {str(e)}")

    def get_cached_questions(self, doc_id: str) -> Optional[Dict]:
        """Retrieve cached questions if available"""
        try:
            doc = self.search_client.get_document(key=f"{doc_id}-questions")
            return json.loads(doc["content"])
        except:
            return None
        

    def _answer_question(self, doc_id: str, question: str, title: str) -> Dict:
        """Answer question about the paper"""
        try:
            # Get relevant content
            results = self.search_client.search(
                search_text=question,
                vector_queries=[{
                    "fields": "content_vector",
                    "kind": "vector",
                    "vector": self._get_embedding(question),
                    "k": 3
                }],
                select=["content"],
                top=3
            )
            
            context = "\n".join(
                f"[Excerpt {i+1}]: {hit['content'][:500]}..."
                for i, hit in enumerate(results)
            )

            # Generate answer
            response = self.openai_client.chat.completions.create(
                model=self.CHAT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": f"You are a research assistant analyzing: {title}\n"
                                  "Answer concisely and reference the paper content."
                    },
                    {
                        "role": "user",
                        "content": f"Question: {question}\nPaper Content:\n{context}\n\n"
                                  "Provide a brief answer citing relevant passages."
                    }
                ],
                temperature=0.3,
                max_tokens=300
            )
            
            return {
                "answer": response.choices[0].message.content,
                "sources": [title],
                "doc_id": doc_id
            }
        except Exception as e:
            return {"error": f"Failed to answer question: {str(e)}"}

    # Helper methods
    def _validate_pdf(self, url: str) -> bool:
        """Improved PDF URL validation"""
        try:
            # Check basic URL format
            parsed = urlparse(url)
            if not all([parsed.scheme, parsed.netloc]):
                return False
            
            # Check for PDF extension
            if not (url.lower().endswith('.pdf') or 'pdf' in parsed.path.lower()):
                return False
                
            # Check content type
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
            }
            response = requests.head(url, headers=headers, timeout=10, allow_redirects=True)
            
            # Check both content type and status code
            content_type = response.headers.get('Content-Type', '').lower()
            return (
                response.status_code == 200 and 
                ('application/pdf' in content_type or 'octet-stream' in content_type)
            )
        except Exception as e:
            print(f"URL validation error: {str(e)}")
            return False

    def _generate_doc_id(self, pdf_url: str, title: str) -> str:
        """Generate consistent document ID"""
        return hashlib.sha256(f"{pdf_url}-{title}".encode()).hexdigest()

    def _paper_exists(self, doc_id: str) -> bool:
        """Check if paper is already indexed"""
        try:
            self.search_client.get_document(key=doc_id)
            return True
        except:
            return False

    def _extract_text(self, pdf_url: str) -> Optional[str]:
        """Extract text from PDF"""
        poller = self.document_analysis_client.begin_analyze_document_from_url(
            "prebuilt-read", pdf_url)
        return " ".join(p.content for p in poller.result().paragraphs)

    @lru_cache(maxsize=100)
    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Get cached text embedding"""
        try:
            response = self.openai_client.embeddings.create(
                input=text[:self.MAX_CONTENT_LENGTH],
                model=self.EMBEDDING_MODEL)
            return response.data[0].embedding
        except:
            return None