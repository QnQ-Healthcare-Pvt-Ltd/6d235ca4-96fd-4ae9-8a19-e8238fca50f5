from typing import Dict, Any
import openai
from app.core.config import settings
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatGPTService:
    def __init__(self):
        logger.info("ChatGPT Service initialized")

    async def generate_content(self, config: dict, form_data: dict) -> dict:
        try:
            # Extract configuration
            api_key = config.get('apiKey')
            if not api_key:
                raise ValueError("ChatGPT API key not found in configuration")

            # Initialize OpenAI client with the node's API key
            client = openai.OpenAI(api_key=api_key)
            
            messages = []
            
            if config.get('role') == 'user' and config.get('prompt'):
                # Format form data for context
                form_context = "\n".join([f"{k}: {v}" for k, v in form_data.items()])
                
                # Replace form field placeholders in the prompt
                prompt = config['prompt']
                for field_name, field_value in form_data.items():
                    placeholder = f"{{{{{field_name}}}}}"
                    prompt = prompt.replace(placeholder, str(field_value))
                
                # Add system message with form data context
                messages.append({
                    "role": "system", 
                    "content": f"You are a helpful assistant. Here is the form data for context:\n{form_context}"
                })
                messages.append({"role": "user", "content": prompt})
                
                logger.info(f"Using custom prompt with form data context: {prompt}")
            else:
                # Default assistant behavior
                context = "You are a helpful assistant. Please process the following form data:"
                form_data_str = "\n".join([f"{k}: {v}" for k, v in form_data.items()])
                
                messages.append({"role": "system", "content": context})
                messages.append({"role": "user", "content": form_data_str})
                
                logger.info("Using default assistant behavior")

            # Generate content using OpenAI
            response = client.chat.completions.create(
                model=config.get('model', 'gpt-3.5-turbo'),
                messages=messages,
                temperature=float(config.get('temperature', 0.7)),
                max_tokens=int(config.get('maxTokens', 2000))
            )

            # Extract generated content
            generated_content = response.choices[0].message.content.strip()
            
            logger.info("Content generated successfully")
            return {
                "status": "success",
                "content": generated_content,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
            }

        except Exception as e:
            logger.error(f"Failed to generate content: {str(e)}")
            return {
                "status": "error",
                "message": f"Failed to generate content: {str(e)}"
            }

    def _create_prompt(self, form_data: Dict[str, Any], role: str) -> str:
        """Create a prompt from form data based on the assistant's role"""
        # Convert form data to a formatted string
        form_fields = "\n".join([f"{key}: {value}" for key, value in form_data.items()])
        
        # Create a context-aware prompt
        prompt = (
            f"As a {role}, please generate a response based on the following form submission:\n\n"
            f"{form_fields}\n\n"
            "Please provide a professional and relevant response."
        )
        
        return prompt 