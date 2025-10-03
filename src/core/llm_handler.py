import logging
import json
import re
import time
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass
import ollama
from ollama import Client
from langchain_community.llms import Ollama as LangchainOllama
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Container for LLM response data."""
    content: str
    structured_data: Optional[Dict[str, Any]] = None
    confidence: float = 1.0
    model: str = ""
    duration_ms: float = 0
    error: Optional[str] = None


class OllamaHandler:
    """Handler for Ollama LLM interactions."""
    
    def __init__(self, model: str, base_url: str, timeout: int = 60, 
                 temperature: float = 0.1, max_retries: int = 3):
        """
        Initialize OllamaHandler.
        
        Args:
            model: Ollama model name
            base_url: Base URL for Ollama API
            timeout: Request timeout in seconds
            temperature: Model temperature for generation
            max_retries: Maximum number of retry attempts
        """
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.temperature = temperature
        self.max_retries = max_retries
        
        # Initialize Ollama client
        try:
            self.client = Client(host=base_url)
            self._test_connection()
        except Exception as e:
            logger.error(f"Failed to initialize Ollama client: {e}")
            self.client = None
        
        # Initialize Langchain Ollama for more complex chains
        try:
            self.langchain_llm = LangchainOllama(
                base_url=base_url,
                model=model,
                temperature=temperature,
                timeout=timeout
            )
        except Exception as e:
            logger.warning(f"Failed to initialize Langchain Ollama: {e}")
            self.langchain_llm = None
    
    def _test_connection(self) -> bool:
        """
        Test connection to Ollama server.

        Returns:
            True if connection successful
        """
        try:
            # Try to list models
            response = self.client.list()

            # Extract model list from response
            if hasattr(response, 'get') and 'models' in response:
                # Dictionary response
                model_list = response['models']
            elif hasattr(response, '__iter__') and not isinstance(response, (str, dict)):
                # Iterable response (list, tuple, etc.)
                model_list = list(response)
            else:
                # Direct response
                model_list = [response]

            # Extract model names
            model_names = []
            for m in model_list:
                if hasattr(m, 'model'):
                    # Handle Ollama Model objects with .model attribute
                    model_names.append(m.model)
                elif hasattr(m, 'name'):
                    # Handle objects with .name attribute
                    model_names.append(m.name)
                elif isinstance(m, dict):
                    # Handle dict responses
                    model_names.append(m.get('name', m.get('model', str(m))))
                else:
                    # Fallback to string representation
                    model_names.append(str(m))

            logger.info(f"Connected to Ollama. Available models: {model_names}")

            # Check if requested model is available
            if self.model not in model_names and f"{self.model}:latest" not in model_names:
                logger.warning(f"Model {self.model} not found. Available: {model_names}")
                return False

            return True

        except Exception as e:
            logger.error(f"Ollama connection test failed: {e}")
            return False
    
    def classify(self, content: str, prompt_template: str, 
                options: Optional[List[str]] = None) -> LLMResponse:
        """
        Classify content using LLM.
        
        Args:
            content: Content to classify
            prompt_template: Prompt template with {content} placeholder
            options: Optional list of valid classification options
            
        Returns:
            LLM response with classification
        """
        if not self.client:
            return LLMResponse(
                content="",
                error="Ollama client not initialized"
            )
        
        start_time = time.time()
        
        try:
            # Format prompt
            prompt = prompt_template.format(content=content[:10000])  # Limit content size
            
            if options:
                prompt += f"\n\nValid options: {', '.join(options)}"
                prompt += "\nRespond with only one of the valid options."
            
            # Make request with retries
            for attempt in range(self.max_retries):
                try:
                    response = self.client.generate(
                        model=self.model,
                        prompt=prompt,
                        options={
                            'temperature': self.temperature,
                            'top_p': 0.9,
                            'num_predict': 100  # Limit response length for classification
                        }
                    )
                    
                    if response and 'response' in response:
                        content = response['response'].strip()
                        
                        # Extract confidence if present
                        confidence = self._extract_confidence(content)
                        
                        # Validate against options if provided
                        if options:
                            content = self._validate_classification(content, options)
                        
                        duration_ms = (time.time() - start_time) * 1000
                        
                        return LLMResponse(
                            content=content,
                            confidence=confidence,
                            model=self.model,
                            duration_ms=duration_ms
                        )
                    
                except Exception as e:
                    if attempt < self.max_retries - 1:
                        logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying...")
                        time.sleep(2 ** attempt)  # Exponential backoff
                    else:
                        raise
            
        except Exception as e:
            logger.error(f"Classification failed: {e}")
            return LLMResponse(
                content="",
                error=str(e)
            )
    
    def analyze(self, content: str, prompt_template: str, 
               extract_json: bool = True) -> LLMResponse:
        """
        Analyze content and extract structured data.
        
        Args:
            content: Content to analyze
            prompt_template: Prompt template with {content} placeholder
            extract_json: Whether to extract JSON from response
            
        Returns:
            LLM response with analysis
        """
        if not self.client:
            return LLMResponse(
                content="",
                error="Ollama client not initialized"
            )
        
        start_time = time.time()
        
        try:
            # Format prompt
            prompt = prompt_template.format(content=content[:20000])  # Larger limit for analysis
            
            # Make request with retries
            for attempt in range(self.max_retries):
                try:
                    response = self.client.generate(
                        model=self.model,
                        prompt=prompt,
                        options={
                            'temperature': self.temperature,
                            'top_p': 0.95,
                            'num_predict': 2048  # Allow longer responses
                        }
                    )
                    
                    if response and 'response' in response:
                        content = response['response'].strip()
                        structured_data = None
                        
                        # Extract JSON if requested
                        if extract_json:
                            structured_data = self._parse_json_response(content)
                        
                        duration_ms = (time.time() - start_time) * 1000
                        
                        return LLMResponse(
                            content=content,
                            structured_data=structured_data,
                            model=self.model,
                            duration_ms=duration_ms
                        )
                    
                except Exception as e:
                    if attempt < self.max_retries - 1:
                        logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying...")
                        time.sleep(2 ** attempt)
                    else:
                        raise
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return LLMResponse(
                content="",
                error=str(e)
            )
    
    def extract_fields(self, content: str, fields: List[str], 
                      context: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract specific fields from content.
        
        Args:
            content: Content to extract from
            fields: List of field names to extract
            context: Optional context about the content
            
        Returns:
            Dictionary with extracted fields
        """
        prompt = f"""
        Extract the following information from the provided content:
        
        Fields to extract:
        {chr(10).join(f'- {field}' for field in fields)}
        
        {f'Context: {context}' if context else ''}
        
        Content:
        {content[:10000]}
        
        Respond in JSON format with the extracted fields.
        If a field cannot be found, use null as the value.
        
        Example response format:
        {{
            "field1": "value1",
            "field2": 123,
            "field3": null
        }}
        """
        
        response = self.analyze(prompt, "{content}", extract_json=True)
        
        if response.structured_data:
            return response.structured_data
        
        # Return empty dict with null values if extraction failed
        return {field: None for field in fields}
    
    def _parse_json_response(self, response: str) -> Optional[Dict[str, Any]]:
        """
        Extract JSON from LLM response.
        
        Args:
            response: LLM response text
            
        Returns:
            Parsed JSON data or None
        """
        try:
            # Try to parse entire response as JSON
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # Try to extract JSON from response
        json_patterns = [
            r'\{[^{}]*\}',  # Simple single-level JSON
            r'\{(?:[^{}]|\{[^{}]*\})*\}',  # Nested JSON (one level)
            r'```json\s*(.*?)\s*```',  # JSON in code block
            r'```\s*(.*?)\s*```',  # Generic code block
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, response, re.DOTALL)
            for match in matches:
                try:
                    # Clean up the match
                    if isinstance(match, tuple):
                        match = match[0]
                    
                    # Try to parse
                    data = json.loads(match)
                    if isinstance(data, dict):
                        return data
                except json.JSONDecodeError:
                    continue
        
        # Try to extract key-value pairs manually
        try:
            data = {}
            lines = response.split('\n')
            
            for line in lines:
                # Look for patterns like "key: value" or "key = value"
                if ':' in line:
                    parts = line.split(':', 1)
                elif '=' in line:
                    parts = line.split('=', 1)
                else:
                    continue
                
                if len(parts) == 2:
                    key = parts[0].strip().strip('"\'')
                    value = parts[1].strip().strip('",\'')
                    
                    # Try to parse value as number
                    try:
                        if '.' in value:
                            value = float(value)
                        else:
                            value = int(value)
                    except ValueError:
                        # Keep as string
                        if value.lower() == 'true':
                            value = True
                        elif value.lower() == 'false':
                            value = False
                        elif value.lower() in ['null', 'none']:
                            value = None
                    
                    data[key] = value
            
            return data if data else None
            
        except Exception as e:
            logger.debug(f"Failed to extract structured data: {e}")
            return None
    
    def _extract_confidence(self, response: str) -> float:
        """
        Extract confidence score from response.
        
        Args:
            response: LLM response text
            
        Returns:
            Confidence score (0-1)
        """
        # Look for confidence indicators
        confidence_patterns = [
            r'confidence[:\s]+([0-9.]+)',
            r'confident[:\s]+([0-9.]+)',
            r'certainty[:\s]+([0-9.]+)',
            r'([0-9]{1,3})%\s+(?:confident|sure|certain)',
        ]
        
        for pattern in confidence_patterns:
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                try:
                    value = float(match.group(1))
                    # Convert percentage to 0-1 if needed
                    if value > 1:
                        value = value / 100
                    return min(1.0, max(0.0, value))
                except ValueError:
                    pass
        
        # Check for confidence words
        high_confidence_words = ['definitely', 'certainly', 'absolutely', 'clearly']
        medium_confidence_words = ['probably', 'likely', 'appears', 'seems']
        low_confidence_words = ['possibly', 'maybe', 'might', 'could be']
        
        response_lower = response.lower()
        
        if any(word in response_lower for word in high_confidence_words):
            return 0.9
        elif any(word in response_lower for word in low_confidence_words):
            return 0.5
        elif any(word in response_lower for word in medium_confidence_words):
            return 0.7
        
        return 0.8  # Default confidence
    
    def _validate_classification(self, response: str, valid_options: List[str]) -> str:
        """
        Validate classification against valid options.
        
        Args:
            response: LLM response
            valid_options: List of valid options
            
        Returns:
            Valid option or original response
        """
        # Check for exact match (case-insensitive)
        response_lower = response.lower().strip()
        
        for option in valid_options:
            if option.lower() == response_lower:
                return option
        
        # Check if response contains an option
        for option in valid_options:
            if option.lower() in response_lower:
                return option
        
        # Check for partial matches
        for option in valid_options:
            # Check if option is at the start of response
            if response_lower.startswith(option.lower()):
                return option
        
        # Return original response if no match found
        logger.warning(f"Response '{response}' not in valid options: {valid_options}")
        return response
    
    def create_chain(self, prompt_template: str, 
                    input_variables: List[str]) -> Optional[LLMChain]:
        """
        Create a Langchain chain for complex processing.
        
        Args:
            prompt_template: Template string with variables
            input_variables: List of variable names
            
        Returns:
            LLMChain instance or None
        """
        if not self.langchain_llm:
            logger.error("Langchain LLM not initialized")
            return None
        
        try:
            prompt = PromptTemplate(
                template=prompt_template,
                input_variables=input_variables
            )
            
            chain = LLMChain(
                llm=self.langchain_llm,
                prompt=prompt
            )
            
            return chain
            
        except Exception as e:
            logger.error(f"Failed to create chain: {e}")
            return None
    
    def batch_process(self, items: List[Dict[str, Any]], 
                     prompt_template: str, batch_size: int = 5) -> List[LLMResponse]:
        """
        Process multiple items in batches.
        
        Args:
            items: List of items to process
            prompt_template: Template for each item
            batch_size: Number of items per batch
            
        Returns:
            List of LLM responses
        """
        results = []
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            
            # Combine batch items
            combined_content = "\n---\n".join(
                f"Item {j+1}:\n{item}" for j, item in enumerate(batch)
            )
            
            # Process batch
            response = self.analyze(combined_content, prompt_template)
            results.append(response)
        
        return results
    
    def is_available(self) -> bool:
        """
        Check if Ollama service is available.
        
        Returns:
            True if service is available
        """
        return self.client is not None and self._test_connection()