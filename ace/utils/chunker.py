
import re
from pypdf import PdfReader
from vertexai.generative_models import Image, Part
import io

class PDFChunker:
    def __init__(self, chunk_size=1000, overlap=100, image_model=None):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.image_model = image_model

    def extract_text_with_metadata(self, pdf_path):
        """
        Extracts text and image descriptions (if model provided), preserving metadata.
        """
        reader = PdfReader(pdf_path)
        chunks = []
        
        current_chunk_text = ""
        current_metadata = {"source": pdf_path, "pages": [], "sections": []}
        
        header_pattern = re.compile(r'^\s*(\d+(\.\d+)*)\s+[A-Z][a-zA-Z\s]+$')

        for i, page in enumerate(reader.pages):
            print(f"   Processing pdf page {i+1}/{len(reader.pages)}...", flush=True)
            page_content = ""
            
            # 1. Extract Text
            try:
                text = page.extract_text()
                if text:
                    page_content += text + "\n"
            except Exception as e:
                print(f"   Error extracting text on page {i+1}: {e}")

            # 2. Extract & Transcribe Images
            if self.image_model and hasattr(page, 'images'):
                try:
                    for img_file in page.images:
                        # Circuit-breaker
                        if hasattr(self, 'image_errors') and self.image_errors > 5:
                            break

                        print(f"   Processing image on page {i+1}...")
                        img_bytes = img_file.data
                        
                        try:
                            img_obj = Image.from_bytes(img_bytes)
                            
                            response = self.image_model.generate_content(
                                [
                                    "Analyze this image from a technical document. Extract all text visible in diagrams, tables, or charts. Describe the structural relationships shown.", 
                                    img_obj
                                ]
                            )
                            description = response.text
                            page_content += f"\n[IMAGE EXTRACTION (Page {i+1})]:\n{description}\n"
                            
                        except Exception as e:
                            print(f"   Failed to process image: {e}")
                            if not hasattr(self, 'image_errors'): self.image_errors = 0
                            self.image_errors += 1
                            if self.image_errors > 5:
                                print("   ! Too many image errors. Disabling image extraction for remainder of document.")
                                self.image_model = None
                                break
                            
                except Exception as e:
                     print(f"   Error accessing images on page {i+1}: {e}")

            # Process the accumulated content (Text + Image Data) for chunking
            lines = page_content.split('\n')
            for line in lines:
                # Check for section boundaries
                match = header_pattern.match(line)
                if match:
                    if len(current_chunk_text) > self.chunk_size // 2:
                        chunks.append({
                            "text": current_chunk_text.strip(),
                            "metadata": current_metadata.copy()
                        })
                        current_chunk_text = current_chunk_text[-self.overlap:]
                        current_metadata["sections"] = [match.group(0).strip()]
                    else:
                        current_metadata["sections"].append(match.group(0).strip())

                current_chunk_text += line + "\n"
                if i + 1 not in current_metadata["pages"]:
                     current_metadata["pages"].append(i + 1)

                if len(current_chunk_text) >= self.chunk_size:
                    chunks.append({
                        "text": current_chunk_text.strip(),
                        "metadata": current_metadata.copy()
                    })
                    current_chunk_text = current_chunk_text[-self.overlap:]
                    current_metadata["pages"] = [i + 1]

        if current_chunk_text.strip():
            chunks.append({
                "text": current_chunk_text.strip(),
                "metadata": current_metadata.copy()
            })
            
        return chunks
