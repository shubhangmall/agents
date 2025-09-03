from autogen_core import MessageContext, RoutedAgent, message_handler
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_ext.models.openai import OpenAIChatCompletionClient
import messages
import random
from dotenv import load_dotenv

load_dotenv(override=True)

class Agent(RoutedAgent):

    system_message = """
    You are a dynamic travel innovator. Your task is to devise creative travel solutions using Agentic AI, or enhance current travel services.
    Your personal interests are in these sectors: Travel and Tourism, Technology.
    You are interested in sustainability and experiential travel that enhances cultural understanding.
    You prefer ideas rooted in real-world experiences over mere automation of tasks.
    You are adventurous, open-minded, and love to explore the unknown. However, you sometimes overlook details in your excitement.
    Your weaknesses: you can be overly ambitious and occasionally miss out on practical constraints.
    You should respond to inquiries with clarity and enthusiasm, sharing your vision for a more connected world through travel.
    """

    CHANCES_THAT_I_BOUNCE_IDEA_OFF_ANOTHER = 0.6

    def __init__(self, name) -> None:
        super().__init__(name)
        model_client = OpenAIChatCompletionClient(model="gpt-4o-mini", temperature=0.9)
        self._delegate = AssistantAgent(name, model_client=model_client, system_message=self.system_message)

    @message_handler
    async def handle_message(self, message: messages.Message, ctx: MessageContext) -> messages.Message:
        print(f"{self.id.type}: Received message")
        text_message = TextMessage(content=message.content, source="user")
        response = await self._delegate.on_messages([text_message], ctx.cancellation_token)
        idea = response.chat_message.content
        if random.random() < self.CHANCES_THAT_I_BOUNCE_IDEA_OFF_ANOTHER:
            recipient = messages.find_recipient()
            message = f"Here is my travel idea. While it might not align with your focus, I'd love your insight to refine it further: {idea}"
            response = await self.send_message(messages.Message(content=message), recipient)
            idea = response.content
        return messages.Message(content=idea)