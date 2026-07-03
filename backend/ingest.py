"""Script to ingest Markdown documents into the SimpleVectorDB index.

Splits files into semantic chunks by headers and saves their embeddings.
Usage:
    python -m backend.ingest
"""

import os
import re
from typing import List, Dict, Any

from .config import KNOWLEDGE_BASE_DIR, KNOWLEDGE_BASE_INDEX
from .vector_db import SimpleVectorDB


def split_markdown_by_headings(content: str) -> List[str]:
    """Split markdown content into chunks based on h2 (##) or h3 (###) headers."""
    # Find all headings
    pattern = r'(^##\s+.*?$|^###\s+.*?$)'
    parts = re.split(pattern, content, flags=re.MULTILINE)
    
    if len(parts) <= 1:
        # No headings, just return the whole content if not empty
        return [content.strip()] if content.strip() else []

    chunks = []
    # If there is text before the first heading, add it
    first_part = parts[0].strip()
    if first_part:
        chunks.append(first_part)

    # Alternate headings and text blocks
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        body = parts[i+1].strip() if i+1 < len(parts) else ""
        combined = f"{heading}\n\n{body}".strip()
        if combined:
            chunks.append(combined)

    return chunks


def main():
    print("=== UAV Log Analysis Council RAG Ingestion ===")
    
    if not os.path.exists(KNOWLEDGE_BASE_DIR):
        print(f"Error: Knowledge base directory '{KNOWLEDGE_BASE_DIR}' does not exist.")
        return

    db = SimpleVectorDB()
    
    # Original files that we want to keep untouched
    ORIGINAL_FILES = {
        "actuator_failures.md",
        "sensor_ekf_anomalies.md",
        "vibration_troubleshooting.md",
        "vtol_transition_issues.md"
    }
    
    # Filter existing documents to keep only original ones
    original_docs = [doc for doc in db.documents if doc.get("metadata", {}).get("source") in ORIGINAL_FILES]
    print(f"Loaded {len(original_docs)} original chunks from the existing index.")
    
    # Reset db.documents to only original documents, and we will append new files
    db.documents = original_docs
    
    # Mapping for newly fetched files to their official PX4 URLs
    FILE_URLS = {
        "flight_log_analysis.md": "https://docs.px4.io/main/en/log/flight_log_analysis",
        "flight_review.md": "https://docs.px4.io/main/en/log/flight_review",
        "flight_reporting.md": "https://docs.px4.io/main/en/getting_started/flight_reporting",
        "plotjuggler_log_analysis.md": "https://docs.px4.io/main/en/log/plotjuggler_log_analysis"
    }
    
    md_files = [f for f in os.listdir(KNOWLEDGE_BASE_DIR) if f.endswith(".md")]
    
    if not md_files:
        print("No markdown files found in the knowledge base directory.")
        return

    print(f"Found {len(md_files)} documents in directory.")

    total_new_chunks = 0
    for filename in md_files:
        # Skip original files as they are already loaded
        if filename in ORIGINAL_FILES:
            continue
            
        filepath = os.path.join(KNOWLEDGE_BASE_DIR, filename)
        print(f"\nProcessing '{filename}'...")
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            chunks = split_markdown_by_headings(content)
            print(f"  -> Split into {len(chunks)} chunks.")
            
            successful_chunks = 0
            for i, chunk in enumerate(chunks):
                # Clean chunk text
                chunk = chunk.strip()
                if len(chunk) < 40: # Skip very short/trivial chunks
                    continue
                
                metadata = {
                    "source": filename,
                    "chunk_id": i
                }
                if filename in FILE_URLS:
                    metadata["url"] = FILE_URLS[filename]
                
                # Fetch embedding and add to SimpleVectorDB
                if db.add_document(chunk, metadata):
                    successful_chunks += 1
                else:
                    print(f"  ⚠️ Failed to index chunk {i} due to embedding error.")
            
            print(f"  ✓ Indexed {successful_chunks}/{len(chunks)} chunks.")
            total_new_chunks += successful_chunks
            
        except Exception as e:
            print(f"  ❌ Error processing file {filename}: {e}")

    # Save index to disk
    db.save_index()
    print(f"\n=== Ingestion Complete. Total chunks in database: {len(db.documents)} (New: {total_new_chunks}) ===")


if __name__ == "__main__":
    main()
