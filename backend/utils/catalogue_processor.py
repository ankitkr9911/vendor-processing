"""
CSV Catalogue Processor
Handles immediate CSV parsing and validation (no LLM processing needed)
"""

import pandas as pd
import json
import os
from typing import Dict, List, Any, Tuple
from datetime import datetime


class CatalogueProcessor:
    """Process and validate CSV catalogue files"""
    
    # Required columns based on the provided structure
    REQUIRED_COLUMNS = [
        'Model Name',
        'Years',
        'Vehicle Type',
        'Description'
    ]
    
    OPTIONAL_COLUMNS = [
        'Submodels',
        'Image URL',
        'Page URL'
    ]
    
    def __init__(self):
        pass
    
    def process_csv(self, csv_path: str, vendor_id: str) -> Dict[str, Any]:
        """
        Process CSV catalogue file immediately (Stage 2 - no batching)
        
        Returns:
            {
                'success': bool,
                'products': [...],  # Parsed product array
                'row_count': int,
                'validation_errors': [],
                'confidence': float,
                'processed_at': str
            }
        """
        
        try:
            # Read CSV with Pandas - try multiple encodings
            encodings_to_try = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
            df = None
            last_error = None
            
            for encoding in encodings_to_try:
                try:
                    df = pd.read_csv(csv_path, encoding=encoding)
                    print(f"   ✅ Successfully read CSV with {encoding} encoding")
                    break
                except UnicodeDecodeError as e:
                    last_error = e
                    continue
            
            if df is None:
                raise ValueError(f"Could not decode CSV with any standard encoding. Last error: {last_error}")
            
            # Strip whitespace from column headers
            df.columns = df.columns.str.strip()
            
            # Validation checks
            validation_errors = []
            
            # Check required columns
            missing_cols = [col for col in self.REQUIRED_COLUMNS if col not in df.columns]
            if missing_cols:
                validation_errors.append(f"Missing required columns: {', '.join(missing_cols)}")
            
            # Check for empty dataframe
            if df.empty:
                validation_errors.append("CSV file is empty")
                return {
                    'success': False,
                    'products': [],
                    'row_count': 0,
                    'validation_errors': validation_errors,
                    'confidence': 0.0,
                    'processed_at': datetime.now().isoformat()
                }
            
            # Data quality checks
            row_count = len(df)
            
            # Check for rows with missing critical data
            for idx, row in df.iterrows():
                if pd.isna(row.get('Model Name')) or str(row.get('Model Name')).strip() == '':
                    validation_errors.append(f"Row {idx + 2}: Missing Model Name")
                
                if pd.isna(row.get('Vehicle Type')) or str(row.get('Vehicle Type')).strip() == '':
                    validation_errors.append(f"Row {idx + 2}: Missing Vehicle Type")
            
            # Convert DataFrame to list of dictionaries
            products = df.to_dict('records')
            
            # Clean up NaN values (convert to None for JSON)
            products = self._clean_nan_values(products)
            
            # Calculate confidence based on data completeness
            confidence = self._calculate_confidence(df, validation_errors)
            
            # Determine success
            success = len(validation_errors) == 0 or confidence > 0.7
            
            result = {
                'success': success,
                'products': products,
                'row_count': row_count,
                'validation_errors': validation_errors[:10],  # Limit to first 10 errors
                'confidence': confidence,
                'processed_at': datetime.now().isoformat(),
                'columns': list(df.columns)
            }
            
            print(f"✅ Catalogue processed: {vendor_id}")
            print(f"   Products: {row_count}")
            print(f"   Confidence: {confidence:.2f}")
            print(f"   Errors: {len(validation_errors)}")
            
            return result
            
        except pd.errors.EmptyDataError:
            return {
                'success': False,
                'products': [],
                'row_count': 0,
                'validation_errors': ['CSV file is empty or malformed'],
                'confidence': 0.0,
                'processed_at': datetime.now().isoformat()
            }
        
        except Exception as e:
            print(f"❌ Catalogue processing error for {vendor_id}: {e}")
            return {
                'success': False,
                'products': [],
                'row_count': 0,
                'validation_errors': [f'Processing error: {str(e)}'],
                'confidence': 0.0,
                'processed_at': datetime.now().isoformat()
            }
    
    def _clean_nan_values(self, products: List[Dict]) -> List[Dict]:
        """Convert pandas NaN to None for JSON serialization"""
        cleaned = []
        for product in products:
            cleaned_product = {}
            for key, value in product.items():
                if pd.isna(value):
                    cleaned_product[key] = None
                else:
                    cleaned_product[key] = value
            cleaned.append(cleaned_product)
        return cleaned
    
    def _calculate_confidence(self, df: pd.DataFrame, errors: List[str]) -> float:
        """
        Calculate catalogue data quality confidence score
        
        Factors:
        - Required columns present: 0.3
        - Data completeness: 0.4
        - Valid data formats: 0.3
        """
        score = 0.0
        
        # Required columns present
        has_required = all(col in df.columns for col in self.REQUIRED_COLUMNS)
        if has_required:
            score += 0.3
        
        # Data completeness (% of non-null values in required columns)
        if has_required:
            completeness_scores = []
            for col in self.REQUIRED_COLUMNS:
                non_null_ratio = df[col].notna().sum() / len(df)
                completeness_scores.append(non_null_ratio)
            
            avg_completeness = sum(completeness_scores) / len(completeness_scores)
            score += avg_completeness * 0.4
        
        # Error penalty
        error_penalty = min(len(errors) * 0.05, 0.3)
        score -= error_penalty
        
        return max(0.0, min(1.0, score))
    
    def save_to_extracted_folder(self, result: Dict[str, Any], vendor_id: str, vendor_base_path: str) -> str:
        """
        Save processed catalogue to extracted/ folder
        
        Args:
            result: Processing result from process_csv()
            vendor_id: Vendor ID
            vendor_base_path: Base path to vendor folder
        
        Returns:
            Path to saved JSON file
        """
        extracted_folder = os.path.join(vendor_base_path, "extracted")
        os.makedirs(extracted_folder, exist_ok=True)
        
        output_path = os.path.join(extracted_folder, "catalogue_data.json")
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Saved catalogue data: {output_path}")
        
        return output_path
    
    def validate_filename(self, filename: str) -> bool:
        """Check if filename matches expected pattern"""
        filename_lower = filename.lower()
        
        # Accept various catalogue naming patterns
        valid_patterns = [
            'catalogue',
            'catalog',
            'product',
            'inventory'
        ]
        
        # Must be CSV
        if not filename_lower.endswith('.csv'):
            return False
        
        # Check if any valid pattern is in filename
        return any(pattern in filename_lower for pattern in valid_patterns)


# Global instance
catalogue_processor = CatalogueProcessor()
