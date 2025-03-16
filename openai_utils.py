import os
from models_config import get_env_variable_keys
from openai import AzureOpenAI

class OpenAIClient:
    def __init__(self, model_id="gpt4o_2"):
        """Initialize the OpenAI client with the specified model ID."""
        self.model_id = model_id
        self.deployment_name = ""
        self.client = self._get_client()

    def _get_client(self):
        """Set up and return an AzureOpenAI client instance."""
        env_keys = get_env_variable_keys(self.model_id)

        endpoint = os.getenv(env_keys["endpoint"])
        api_key = os.getenv(env_keys["api_key"])
        api_version = os.getenv(env_keys["api_version"])
        self.deployment_name = os.getenv(env_keys["deployment_name"])

        if not all([endpoint, api_key, api_version, self.deployment_name]):
            missing = [key for key, val in env_keys.items() if not os.getenv(val)]
            raise ValueError(f"Missing environment variables: {', '.join(missing)}")

        return AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
            max_retries=0,
            timeout=15
        )

    def call_openai(self, message: str):
        """Send a message to OpenAI and return the response."""
        response = self.client.chat.completions.create(
            model=self.deployment_name,
            messages=[{"role": "user", "content": message}],
            max_tokens=100,
        )

        if response and response.choices:
            return response.usage.total_tokens


_default_client = OpenAIClient()

def call_openai(message: str):
    """Convenience function to call OpenAI using the default client."""
    return _default_client.call_openai(message)