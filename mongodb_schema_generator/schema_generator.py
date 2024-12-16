import os
import yaml
from typing import Dict, List, Optional, Set
from pathlib import Path
import anthropic
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection
import sys
import re
from collections import defaultdict
import logging
import time
import asyncio

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class SchemaGenerator:
    def __init__(self, config_path: str):
        """Initialize the schema generator with configuration."""
        try:
            with open(config_path, 'r') as f:
                self.config = yaml.safe_load(f)

            # Initialize MongoDB client
            self.client = MongoClient(os.getenv('MONGODB_URI'))
            self.db = self.client[self.config['mongodb']['database']]
            self.collections = self.db.list_collection_names()

            # Initialize Claude client
            self.claude_api_key = os.getenv('CLAUDE_API_KEY')
            if not self.claude_api_key:
                raise ValueError("CLAUDE_API_KEY environment variable is not set")
            self.claude_client = anthropic.Client(api_key=self.claude_api_key)
            logger.info("Successfully initialized Claude API client")

        except Exception as e:
            logger.error(f"Error initializing schema generator: {str(e)}")
            raise

    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from YAML file."""
        try:
            logger.info(f"Loading configuration from {config_path}")
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info("Configuration loaded successfully")
            return config
        except Exception as e:
            logger.error(f"Error loading config file: {str(e)}")
            sys.exit(1)
    
    def _connect_mongodb(self) -> MongoClient:
        """Establish connection to MongoDB."""
        try:
            logger.info("Connecting to MongoDB...")
            client = MongoClient(self.config['mongodb']['uri'])
            # Test the connection
            client.admin.command('ping')
            logger.info("Successfully connected to MongoDB")
            return client
        except Exception as e:
            logger.error(f"Error connecting to MongoDB: {str(e)}")
            sys.exit(1)
    
    def _init_claude_client(self):
        """Initialize Claude API client."""
        try:
            logger.info("Initializing Claude API client...")
            api_key = os.getenv('CLAUDE_API_KEY') or self.config['claude']['api_key']
            if not api_key:
                raise ValueError("Claude API key not found in environment or config")
            
            self.claude_client = anthropic.Anthropic(api_key=api_key)
            logger.info("Successfully initialized Claude API client")
        except Exception as e:
            logger.error(f"Error initializing Claude API client: {str(e)}")
            sys.exit(1)
    
    def _get_collection_fields(self, collection: Collection, sample_size: int = 100) -> Dict[str, str]:
        """Get all fields and their types from a collection by sampling documents."""
        try:
            logger.info(f"Analyzing collection '{collection.name}' (sampling {sample_size} documents)...")
            fields = {}
            doc_count = 0
            start_time = time.time()
            
            for doc in collection.aggregate([{"$sample": {"size": sample_size}}]):
                doc_count += 1
                if doc_count % 10 == 0:  # Log progress every 10 documents
                    logger.info(f"Processed {doc_count}/{sample_size} documents in {collection.name}")
                fields.update(self._get_document_fields_with_types(doc))
            
            elapsed_time = time.time() - start_time
            logger.info(f"Completed analysis of '{collection.name}' - Found {len(fields)} unique fields in {elapsed_time:.2f} seconds")
            return fields
        except Exception as e:
            logger.error(f"Error getting collection fields for '{collection.name}': {str(e)}")
            return {}

    def _get_document_fields_with_types(self, doc: Dict, prefix: str = "") -> Dict[str, str]:
        """Recursively get all fields and their types from a document."""
        fields = {}
        for key, value in doc.items():
            if key == "_id":
                continue
            field_name = f"{prefix}{key}" if prefix else key
            
            # Determine field type
            if isinstance(value, str):
                fields[field_name] = "string"
            elif isinstance(value, bool):
                fields[field_name] = "boolean"
            elif isinstance(value, int):
                fields[field_name] = "integer"
            elif isinstance(value, float):
                fields[field_name] = "float"
            elif isinstance(value, list):
                if value and isinstance(value[0], str):
                    fields[field_name] = "string[]"
                else:
                    fields[field_name] = "array"
            elif isinstance(value, dict):
                fields[field_name] = "json"
                nested_fields = self._get_document_fields_with_types(value, f"{field_name}.")
                fields.update(nested_fields)
            else:
                fields[field_name] = "string"  # default to string for unknown types
                
        return fields

    def _identify_relationships(self, collections_schema: Dict[str, Dict[str, str]]) -> List[tuple]:
        """Identify relationships between collections based on field names."""
        logger.info("Identifying relationships between collections...")
        relationships = []
        id_pattern = re.compile(r'([A-Za-z]+)Id$')
        
        for collection_name, fields in collections_schema.items():
            logger.info(f"Analyzing relationships for collection '{collection_name}'...")
            relationship_count = 0
            for field_name in fields.keys():
                match = id_pattern.match(field_name)
                if match:
                    referenced_collection = match.group(1).lower()
                    # Check if the referenced collection exists (in plural or singular form)
                    for coll in collections_schema.keys():
                        if (referenced_collection in coll.lower() or 
                            referenced_collection + 's' in coll.lower() or 
                            referenced_collection + 'es' in coll.lower()):
                            relationships.append((collection_name, "||--o{", coll, f": references"))
                            relationship_count += 1
                            logger.info(f"Found relationship: {collection_name} -> {coll} (via {field_name})")
            
            logger.info(f"Found {relationship_count} relationships for '{collection_name}'")
        
        logger.info(f"Total relationships identified: {len(relationships)}")
        return relationships

    async def _validate_with_claude(self, content):
        """
        Validate and clean up the Mermaid diagram content using Claude
        """
        prompt = f"""
        You are a MongoDB schema validator. Please review and fix the following Mermaid diagram:
        1. Remove any duplicate type declarations (e.g., 'string string' should be just 'string')
        2. Ensure proper spacing between entities
        3. Fix any syntax errors
        4. Keep field names with underscores (dots should already be replaced)
        5. Return only the fixed Mermaid diagram, nothing else

        Here's the diagram to fix:

        {content}
        """

        try:
            response = self.claude_client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=4096,
                temperature=0,
                system="You are a MongoDB schema validator. Only output the fixed Mermaid diagram.",
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            # Wait for the response
            response_text = response.content[0].text if response and hasattr(response, 'content') else content
            logger.info(f"Claude response: {response_text}")
            
            # Extract the diagram from the response
            diagram_lines = []
            in_diagram = False
            
            for line in response_text.split('\n'):
                line = line.strip()
                if line == 'erDiagram':
                    in_diagram = True
                    diagram_lines.append(line)
                elif in_diagram:
                    if line and not line.startswith('```'):
                        diagram_lines.append(line)
                    elif line.startswith('```'):
                        in_diagram = False
            
            return '\n'.join(diagram_lines)
        
        except Exception as e:
            logger.error(f"Error validating diagram with Claude: {str(e)}")
            # Return original diagram if Claude validation fails
            return content

    async def _cleanup_diagram(self, content):
        # First validate with Claude if available
        if self.claude_client:
            try:
                content = await self._validate_with_claude(content)
            except Exception as e:
                logger.error(f"Error validating with Claude: {str(e)}")
        
        cleaned_lines = []
        current_entity = None
        
        for line in content.split('\n'):
            line = line.replace('.', '_')
            
            # Skip empty lines and erDiagram line
            if not line.strip() or line.strip() == 'erDiagram':
                cleaned_lines.append(line.strip())
                continue
            
            # Handle entity declarations
            if '{' in line:
                current_entity = line.strip().replace('.', '_').split(' ')[0]
                cleaned_lines.append(f"{current_entity} {'{'}") 
                continue
            elif '}' in line:
                cleaned_lines.append('}')
                current_entity = None
                continue
            
            # Handle field declarations
            if ':' in line and not line.strip().endswith('{'):
                parts = line.strip().split(':')
                field_name = parts[0].strip().replace('.', '_')
                field_type = parts[1].strip()
                cleaned_lines.append(f"    {field_name} {field_type}")
            else:
                # Handle other lines within entity
                if current_entity:
                    field_name = line.strip().split(' ')[0]
                    field_name = field_name.replace('.', '_')
                    remaining = ' '.join(line.strip().split(' ')[1:])
                    cleaned_lines.append(f"    {field_name} {remaining}")
                else:
                    cleaned_lines.append(line.strip())
            
        return '\n'.join(cleaned_lines)

    async def _generate_unified_schema(self, collections_schema: Dict[str, Dict[str, str]], relationships: List[tuple]) -> str:
        """Generate a unified schema for all collections."""
        logger.info("Generating unified schema...")
        
        # Start the Mermaid diagram content
        schema_content = ""
        
        # Process each collection
        for collection_name, fields in collections_schema.items():
            logger.info(f"Processing collection: {collection_name}")
            
            # Start the entity definition
            schema_content += f"{collection_name} {{\n"
            
            # Add fields
            for field_name, field_type in fields.items():
                # Handle nested fields
                if isinstance(field_type, dict):
                    # Flatten nested structure with dot notation
                    flattened_fields = self._flatten_nested_fields(field_type, field_name)
                    for nested_name, nested_type in flattened_fields.items():
                        schema_content += f"    {nested_type} {nested_name}\n"
                else:
                    schema_content += f"    {field_type} {field_name}\n"
            
            schema_content += "}\n\n"
            
        # Add relationships
        for source, relation_type, target, label in relationships:
            schema_content += f"    {source} {relation_type} {target} {label}\n"
        
        # Clean up the diagram
        logger.info("Cleaning up diagram format...")
        cleaned_diagram = await self._cleanup_diagram(schema_content)
        
        # Format the final output with proper headers
        final_content = "erDiagram\n"
        final_content += cleaned_diagram
        final_content += "\n```\n"
        
        logger.info("Unified schema generation completed")
        return final_content

    def _flatten_nested_fields(self, nested_dict, parent_key=''):
        """Flatten nested dictionary fields using dot notation."""
        flattened = {}
        for key, value in nested_dict.items():
            new_key = f"{parent_key}_{key}" if parent_key else key
            
            if isinstance(value, dict):
                # Recursively flatten nested dictionaries
                flattened.update(self._flatten_nested_fields(value, new_key))
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                # Handle array of objects
                flattened[new_key] = "array"
                # Flatten the structure of array items
                sample_item = value[0]
                flattened.update(self._flatten_nested_fields(sample_item, new_key + "_item"))
            else:
                # Convert MongoDB/Python types to simplified schema types
                flattened[new_key] = self._get_simplified_type(value)
        
        return flattened

    def _get_simplified_type(self, value):
        """Convert MongoDB/Python types to simplified schema types."""
        if isinstance(value, list):
            if value:
                # If array has items, use first item's type
                return f"array<{self._get_simplified_type(value[0])}>"
            return "array"
        elif isinstance(value, dict):
            return "json"
        elif isinstance(value, bool):
            return "boolean"
        elif isinstance(value, int):
            return "integer"
        elif isinstance(value, float):
            return "float"
        elif isinstance(value, str):
            return "string"
        else:
            return "unknown"

    async def generate_schemas(self) -> None:
        """Generate schemas for all collections in the database."""
        try:
            start_time = time.time()
            logger.info("Starting schema generation...")
            
            # Create output directory if it doesn't exist
            output_dir = Path(self.config['output']['directory'])
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # First, gather all collection schemas with field types
            collections_schema = {}
            for i, collection_name in enumerate(self.collections, 1):
                logger.info(f"Processing collection {i}/{len(self.collections)}: {collection_name}")
                collection = self.db[collection_name]
                fields = self._get_collection_fields(collection, self.config['schema']['sample_size'])
                
                if not fields:
                    logger.warning(f"No fields found in collection {collection_name}")
                    continue
                
                # Apply field filters
                if self.config['schema']['include_fields']:
                    fields = {k: v for k, v in fields.items() if k in self.config['schema']['include_fields']}
                fields = {k: v for k, v in fields.items() if k not in self.config['schema']['exclude_fields']}
                
                collections_schema[collection_name] = fields
                logger.info(f"Completed processing '{collection_name}' - Found {len(fields)} fields")
            
            # Identify relationships between collections
            relationships = self._identify_relationships(collections_schema)
            
            # Generate ER diagram
            logger.info("Generating ER diagram...")
            er_diagram = await self._generate_unified_schema(collections_schema, relationships)
            
            # Save unified schema
            output_file = output_dir / f"unified_database_schema.{self.config['output']['format']}"
            logger.info(f"Saving ER diagram to {output_file}")
            
            with open(output_file, 'w') as f:
                f.write(er_diagram)
            
            elapsed_time = time.time() - start_time
            logger.info(f"Schema generation completed in {elapsed_time:.2f} seconds")
            logger.info(f"ER diagram saved to {output_file}")
            logger.info("Schema generation completed successfully")
            
        except Exception as e:
            logger.error(f"Error generating schemas: {str(e)}")
            raise

async def main():
    schema_generator = SchemaGenerator('config.yaml')
    await schema_generator.generate_schemas()

if __name__ == "__main__":
    asyncio.run(main())
