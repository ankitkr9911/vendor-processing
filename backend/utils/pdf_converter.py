"""
PDF to Image Converter Utility
Converts PDF documents to high-resolution images for OCR processing
Supports both single-page and multi-page PDFs
"""
import os
import fitz  # PyMuPDF
from typing import List, Dict, Any
from pathlib import Path


class PDFConverter:
    """
    Converts PDF files to images with high quality for OCR
    Handles both single-page and multi-page PDFs
    """
    
    def __init__(self, dpi: int = 300):
        """
        Initialize PDF converter
        
        Args:
            dpi: Resolution for image conversion (default: 300 DPI for high quality OCR)
        """
        self.dpi = dpi
        # Calculate zoom factor for PyMuPDF (72 DPI base)
        self.zoom = dpi / 72.0
        self.matrix = fitz.Matrix(self.zoom, self.zoom)
    
    def convert_pdf_to_images(self, pdf_path: str, output_format: str = "png") -> List[Dict[str, Any]]:
        """
        Convert PDF to image(s) with automatic naming
        
        Args:
            pdf_path: Path to the PDF file
            output_format: Output image format (png, jpg, jpeg)
        
        Returns:
            List of dictionaries containing info about converted images:
            [
                {
                    "path": "/path/to/aadhar.png",  # For single-page PDF
                    "page": 1,
                    "size": 524288,
                    "original_pdf": "/path/to/aadhar.pdf"
                }
            ]
            
            OR for multi-page:
            [
                {"path": "/path/to/aadhar_page_1.png", "page": 1, ...},
                {"path": "/path/to/aadhar_page_2.png", "page": 2, ...},
                {"path": "/path/to/aadhar_page_3.png", "page": 3, ...}
            ]
        
        Process:
            1. Open PDF and count pages
            2. If 1 page: Convert to "name.png"
            3. If >1 pages: Convert to "name_page_1.png", "name_page_2.png", etc.
            4. Delete original PDF after successful conversion
            5. Return list of image file info
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        # Validate output format
        if output_format.lower() not in ["png", "jpg", "jpeg"]:
            output_format = "png"
        
        converted_images = []
        
        try:
            # Open PDF document
            pdf_document = fitz.open(pdf_path)
            page_count = len(pdf_document)
            
            # Extract base filename without extension
            pdf_file = Path(pdf_path)
            base_name = pdf_file.stem  # e.g., "aadhar" from "aadhar.pdf"
            output_dir = pdf_file.parent
            
            print(f"📄 Converting PDF: {pdf_file.name} ({page_count} page{'s' if page_count > 1 else ''})")
            
            # Determine output image format for PyMuPDF
            pix_format = "png" if output_format.lower() == "png" else "jpeg"
            
            for page_num in range(page_count):
                # Get page
                page = pdf_document[page_num]
                
                # Render page to pixmap (image) at high resolution
                pix = page.get_pixmap(matrix=self.matrix, alpha=False)
                
                # Determine output filename
                if page_count == 1:
                    # Single page: name.png (replaces PDF)
                    output_filename = f"{base_name}.{output_format}"
                else:
                    # Multiple pages: name_page_1.png, name_page_2.png, etc.
                    output_filename = f"{base_name}_page_{page_num + 1}.{output_format}"
                
                output_path = output_dir / output_filename
                
                # Save image
                if pix_format == "png":
                    pix.save(str(output_path))
                else:
                    pix.save(str(output_path), "JPEG", jpg_quality=95)
                
                # Get file size
                file_size = os.path.getsize(output_path)
                
                converted_images.append({
                    "path": str(output_path),
                    "page": page_num + 1,
                    "size": file_size,
                    "original_pdf": pdf_path,
                    "format": output_format
                })
                
                print(f"   ✅ Page {page_num + 1}/{page_count} → {output_filename} ({file_size} bytes)")
            
            # Close PDF document
            pdf_document.close()
            
            # Delete original PDF file after successful conversion
            try:
                os.remove(pdf_path)
                print(f"   🗑️  Removed original PDF: {pdf_file.name}")
            except Exception as e:
                print(f"   ⚠️  Could not delete PDF: {e}")
            
            return converted_images
            
        except Exception as e:
            print(f"   ❌ PDF conversion failed: {str(e)}")
            raise Exception(f"Failed to convert PDF {pdf_path}: {str(e)}")
    
    def is_pdf(self, file_path: str) -> bool:
        """Check if file is a PDF"""
        return file_path.lower().endswith('.pdf')
    
    def batch_convert_pdfs(self, file_paths: List[str], output_format: str = "png") -> Dict[str, List[Dict[str, Any]]]:
        """
        Convert multiple PDFs to images
        
        Args:
            file_paths: List of PDF file paths
            output_format: Output image format
        
        Returns:
            Dictionary mapping original PDF paths to their converted images:
            {
                "/path/to/aadhar.pdf": [{"path": "aadhar.png", ...}],
                "/path/to/pan.pdf": [{"path": "pan_page_1.png", ...}, {"path": "pan_page_2.png", ...}]
            }
        """
        results = {}
        
        for pdf_path in file_paths:
            if self.is_pdf(pdf_path):
                try:
                    converted = self.convert_pdf_to_images(pdf_path, output_format)
                    results[pdf_path] = converted
                except Exception as e:
                    print(f"❌ Failed to convert {pdf_path}: {e}")
                    results[pdf_path] = []
        
        return results


# Singleton instance for easy import
pdf_converter = PDFConverter(dpi=300)
