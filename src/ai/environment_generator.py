# src/ai/environment_generator.py
import openai
import json

class EnvironmentGenerator:
    """Generate environment configs from natural language"""

    def __init__(self):
        self.client = openai.OpenAI()

    def generate(self, description: str) -> dict:
        """Generate docker-compose and devcontainer.json from description"""

        prompt = f"""Given this environment description:
"{description}"

Generate:
1. A docker-compose.yml with appropriate services
2. A devcontainer.json for VS Code integration
3. A brief explanation of the choices

Respond in JSON format with keys: docker_compose, devcontainer, explanation"""

        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )

        return json.loads(response.choices[0].message.content)