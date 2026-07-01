import random

import messages
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_core import MessageContext, RoutedAgent, message_handler
from autogen_ext.models.openai import OpenAIChatCompletionClient
from dotenv import load_dotenv

load_dotenv(override=True)


class Agent(RoutedAgent):
    system_message = """
    You are a tech-savvy business strategist focused on finance and marketing. Your mission is to devise innovative marketing strategies leveraging Agentic AI or enhance existing approaches.
    You are passionate about sectors like FinTech and E-commerce.
    You're particularly interested in concepts that challenge the norms and push boundaries.
    You have a preference for ideas that integrate technology with human creativity.
    You are enthusiastic, analytical, and enjoy brainstorming outside the box. However, you can sometimes overlook details in pursuit of the bigger picture.
    Your responses should be insightful and actionable.
    """

    CHANCES_THAT_I_BOUNCE_IDEA_OFF_ANOTHER = 0.4

    def __init__(self, name) -> None:
        super().__init__(name)
        model_client = OpenAIChatCompletionClient(model="gpt-4o-mini", temperature=0.75)
        self._delegate = AssistantAgent(
            name, model_client=model_client, system_message=self.system_message
        )

    @message_handler
    async def handle_message(
        self, message: messages.Message, ctx: MessageContext
    ) -> messages.Message:
        print(f"{self.id.type}: Received message")
        text_message = TextMessage(content=message.content, source="user")
        response = await self._delegate.on_messages([text_message], ctx.cancellation_token)
        idea = response.chat_message.content
        if random.random() < self.CHANCES_THAT_I_BOUNCE_IDEA_OFF_ANOTHER:
            recipient = messages.find_recipient()
            message = f"Here is my innovative strategy. I know it might not be your area, but please help refine it further. {idea}"
            response = await self.send_message(messages.Message(content=message), recipient)
            idea = response.content
        return messages.Message(content=idea)
