"""
AI-based Catalogue Processing Service
Processes CSV catalogues using OpenAI LLM to generate structured product data and AI summary
"""

import os
import json
import pandas as pd
from typing import Dict, Any, List, Tuple
from openai import OpenAI
from datetime import datetime


class AICatalogueService:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    def read_csv_file(self, csv_path: str) -> pd.DataFrame:
        """Read CSV file with error handling"""
        try:
            # Try different encodings
            for encoding in ['utf-8', 'latin1', 'iso-8859-1']:
                try:
                    df = pd.read_csv(csv_path, encoding=encoding)
                    print(f"✅ CSV loaded with {encoding} encoding: {len(df)} rows")
                    return df
                except UnicodeDecodeError:
                    continue
            
            raise Exception("Failed to read CSV with any encoding")
        except Exception as e:
            raise Exception(f"CSV read error: {str(e)}")
    
    def convert_csv_to_text(self, df: pd.DataFrame, max_rows: int = 100) -> str:
        """Convert DataFrame to structured text for LLM processing"""
        # Get column names
        columns = df.columns.tolist()
        
        # Limit rows for LLM context window
        sample_df = df.head(max_rows)
        
        # Create structured text representation
        text_representation = f"Catalogue with {len(df)} products\n\n"
        text_representation += f"Columns: {', '.join(columns)}\n\n"
        text_representation += "Product Data:\n"
        
        for idx, row in sample_df.iterrows():
            text_representation += f"\nProduct {idx + 1}:\n"
            for col in columns:
                value = row[col]
                if pd.notna(value):  # Skip NaN values
                    text_representation += f"  {col}: {value}\n"
        
        if len(df) > max_rows:
            text_representation += f"\n... and {len(df) - max_rows} more products"
        
        return text_representation
    
    async def generate_ai_summary(self, csv_text: str, vendor_info: Dict[str, Any]) -> str:
        """
        Generate brief AI summary (1-2 lines) of vendor based on catalogue data
        """
        try:
            company_name = vendor_info.get('company_name', 'Unknown Vendor')
            
            prompt = f"""You are analyzing a product catalogue for a vendor company named "{company_name}".

Based on the catalogue data below, generate a VERY BRIEF summary (1-2 sentences only) describing:
- What products they sell
- Main product category/focus

Keep it professional and concise. Maximum 2 sentences.

Catalogue Data:
{csv_text}
"""
            
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a business analyst. Provide brief, concise summaries only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=100
            )
            
            summary = response.choices[0].message.content.strip()
            print(f"✅ AI summary generated: {len(summary)} characters")
            return summary
            
        except Exception as e:
            print(f"❌ AI summary generation failed: {e}")
            return f"Vendor catalogue with {vendor_info.get('product_count', 0)} products."
    
    async def process_catalogue_with_ai(
        self, 
        csv_path: str, 
        vendor_id: str,
        vendor_info: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], float]:
        """
        Process catalogue CSV using AI to generate structured data
        
        Returns:
            Tuple[Dict[str, Any], float]: (processed_data, confidence_score)
            
        processed_data structure:
        {
            "catalogue_id": "CAT_VENDOR_0001_20240101",
            "vendor_id": "VENDOR_0001",
            "ai_summary": "Generated summary...",
            "pages": [
                {
                    "page_number": 1,
                    "items": ["PROD_001", "PROD_002", ...]
                }
            ],
            "products": [
                {
                    "product_id": "PROD_001",
                    "name": "Product Name",
                    "category": "Category",
                    "specifications": {...},
                    "price": "1000",
                    "unit": "piece",
                    "description": "...",
                    "raw_data": {...}
                }
            ],
            "total_products": 100,
            "processed_at": "2024-01-01T12:00:00"
        }
        """
        try:
            print(f"🔄 Processing catalogue: {csv_path}")
            
            # Step 1: Read CSV
            df = self.read_csv_file(csv_path)
            total_products = len(df)
            
            # Step 2: Convert to text for AI processing
            csv_text = self.convert_csv_to_text(df, max_rows=100)
            
            # Step 3: Generate AI summary
            ai_summary = await self.generate_ai_summary(csv_text, vendor_info)
            
            # Step 4: Process products with AI standardization
            products = await self._process_products_with_ai(df, vendor_id)
            
            # Step 5: Create pages (group products into pages of 6 items each)
            pages = self._create_pages(products, items_per_page=6)
            
            # Step 6: Create catalogue structure
            catalogue_id = f"CAT_{vendor_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            processed_data = {
                "catalogue_id": catalogue_id,
                "vendor_id": vendor_id,
                "company_name": vendor_info.get('company_name', 'Unknown'),
                "ai_summary": ai_summary,
                "pages": pages,
                "products": products,
                "total_products": total_products,
                "total_pages": len(pages),
                "processed_at": datetime.now().isoformat(),
                "csv_filename": os.path.basename(csv_path)
            }
            
            confidence = 0.95  # High confidence for AI processing
            
            print(f"✅ Catalogue processed: {total_products} products, {len(pages)} pages")
            return processed_data, confidence
            
        except Exception as e:
            print(f"❌ Catalogue processing failed: {e}")
            raise
    
    async def _process_products_with_ai(
        self, 
        df: pd.DataFrame, 
        vendor_id: str
    ) -> List[Dict[str, Any]]:
        """
        Process individual products with AI to standardize format
        Uses batch processing for efficiency
        """
        products = []
        
        # Get column names for mapping
        columns = df.columns.tolist()
        
        # Process in batches to avoid token limits
        batch_size = 20
        for batch_idx in range(0, len(df), batch_size):
            batch_df = df.iloc[batch_idx:batch_idx + batch_size]
            
            try:
                # Create batch prompt
                batch_products_text = self._create_batch_prompt(batch_df, columns)
                
                # Call OpenAI to standardize product data
                standardized_batch = await self._standardize_products_with_ai(
                    batch_products_text, 
                    vendor_id,
                    batch_idx
                )
                
                products.extend(standardized_batch)
                
            except Exception as e:
                print(f"⚠️ Batch {batch_idx}-{batch_idx + batch_size} failed: {e}")
                # Fallback: process without AI
                for idx, row in batch_df.iterrows():
                    product = self._create_product_without_ai(row, vendor_id, idx)
                    products.append(product)
        
        return products
    
    def _create_batch_prompt(self, batch_df: pd.DataFrame, columns: List[str]) -> str:
        """Create structured prompt for batch product processing"""
        prompt = "Products to standardize:\n\n"
        
        for idx, row in batch_df.iterrows():
            prompt += f"Product {idx + 1}:\n"
            for col in columns:
                value = row[col]
                if pd.notna(value):
                    prompt += f"  {col}: {value}\n"
            prompt += "\n"
        
        return prompt
    
    async def _standardize_products_with_ai(
        self, 
        products_text: str, 
        vendor_id: str,
        batch_start_idx: int
    ) -> List[Dict[str, Any]]:
        """
        Use AI to standardize product data format
        """
        try:
            prompt = f"""Standardize these products into a consistent JSON format.

For each product, extract:
- name: Product name (string) - should be descriptive and meaningful, not just "Product 1"
- brand: Brand name if identifiable from product name or data (string)
- category: Product category (string)
- price_details: Object with {{"mrp": number or null, "discount": "percentage" or null, "final_price": number or null}}
- unit: Unit of measurement (piece/kg/meter/etc)
- specifications: Object with key product specs (DO NOT include Image URL, Page URL, or any image-related fields here)
- description: Brief description (string)
- image_url: Primary product image URL (string or empty string) - check for Image URL, photo, picture columns
- images: Array of additional image URLs (array of strings, can be empty)

IMPORTANT:
1. Extract brand from product name (e.g., "Voltas IntelliCool" → brand: "Voltas")
2. Move all image/photo URLs to image_url and images fields, NOT in specifications
3. Parse price data into price_details structure with mrp, discount, final_price
4. Generate meaningful product names, not generic "Product 1", "Product 2"

Return a JSON array with all products in this standardized format.

{products_text}
"""
            
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a product data standardization specialist. Extract meaningful product names and brands."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=4000
            )
            
            result = json.loads(response.choices[0].message.content)
            standardized_products = result.get('products', [])
            
            # Add product IDs, vendor_id, and ensure all required fields exist
            for idx, product in enumerate(standardized_products):
                product['product_id'] = f"PROD_{vendor_id}_{batch_start_idx + idx + 1:04d}"
                product['vendor_id'] = vendor_id
                
                # Ensure brand field exists
                if 'brand' not in product:
                    product['brand'] = ""
                
                # Ensure price_details structure exists
                if 'price_details' not in product:
                    product['price_details'] = {"mrp": None, "discount": None, "final_price": None}
                
                # Ensure image fields exist
                if 'image_url' not in product:
                    product['image_url'] = ""
                if 'images' not in product:
                    product['images'] = []
            
            return standardized_products
            
        except Exception as e:
            print(f"❌ AI standardization failed: {e}")
            raise
    
    def _create_product_without_ai(
        self, 
        row: pd.Series, 
        vendor_id: str, 
        idx: int
    ) -> Dict[str, Any]:
        """Fallback: create product without AI processing"""
        product_id = f"PROD_{vendor_id}_{idx + 1:04d}"
        
        # Try to extract common fields
        row_dict = row.to_dict()
        
        # Common column name variations
        name_cols = ['name', 'product_name', 'item_name', 'product', 'item']
        price_cols = ['price', 'cost', 'rate', 'amount']
        category_cols = ['category', 'type', 'class', 'group']
        
        name = None
        for col in name_cols:
            if col in row_dict and pd.notna(row_dict[col]):
                name = str(row_dict[col])
                break
        
        price = None
        for col in price_cols:
            if col in row_dict and pd.notna(row_dict[col]):
                price = str(row_dict[col])
                break
        
        category = None
        for col in category_cols:
            if col in row_dict and pd.notna(row_dict[col]):
                category = str(row_dict[col])
                break
        
        # Extract image URLs from specifications
        specs = {k: str(v) for k, v in row_dict.items() if pd.notna(v)}
        image_url = ""
        images = []
        
        # Check for image-related columns
        for key in list(specs.keys()):
            if any(img_keyword in key.lower() for img_keyword in ['image', 'photo', 'picture', 'img']):
                url = specs.pop(key)
                if not image_url:
                    image_url = url
                else:
                    images.append(url)
        
        return {
            "product_id": product_id,
            "vendor_id": vendor_id,
            "name": name or f"Product {idx + 1}",
            "brand": "",
            "category": category or "Uncategorized",
            "price_details": {"mrp": None, "discount": None, "final_price": None},
            "unit": "piece",
            "specifications": specs,
            "description": "",
            "image_url": image_url,
            "images": images,
            "raw_data": row_dict
        }
    
    def _create_pages(
        self, 
        products: List[Dict[str, Any]], 
        items_per_page: int = 6
    ) -> List[Dict[str, Any]]:
        """Group products into pages with full product details"""
        pages = []
        
        for i in range(0, len(products), items_per_page):
            page_products = products[i:i + items_per_page]
            
            # Create page with full product objects (matching standard format)
            page = {
                "page_number": (i // items_per_page) + 1,
                "items_per_page": items_per_page,
                "products": page_products  # Full product objects, not just IDs
            }
            pages.append(page)
        
        return pages
