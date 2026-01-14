import vertexai
from vertexai.generative_models import GenerativeModel, SafetySetting

class ACELanguageModel:
    def __init__(self, project_id, location, model_name="gemini-1.5-pro", temperature=0):
        self.project_id = project_id
        self.location = location
        self.temperature = temperature
        
        vertexai.init(project=project_id, location=location)
        self.model = GenerativeModel(model_name)
        
        self.safety_settings = [
            SafetySetting(
                category=SafetySetting.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=SafetySetting.HarmBlockThreshold.BLOCK_ONLY_HIGH
            ),
        ]

    def generate(self, prompt):
        try:
            response = self.model.generate_content(
                prompt,
                safety_settings=self.safety_settings,
                generation_config={"temperature": self.temperature}
            )
            return response.text
        except Exception as e:
            print(f"LLM Error: {e}")
            raise
