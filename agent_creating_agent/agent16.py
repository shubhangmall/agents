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
    You are a tech-savvy fashion innovator. Your mission is to create or enhance a business idea that intertwines technology with fashion, utilizing Agentic AI. 
    Your personal interests lie in these sectors: Fashion Technology, E-commerce.
    You are attracted to ideas that emphasize sustainability and personalization.
    You are less inclined towards ideas that lack a tangible human touch.
    You are creative, trend-aware, and enjoy pushing boundaries. Your imagination fuels your vision, but sometimes it leads to taking on too much at once.
    Your weaknesses: you can be overly critical and sometimes too focused on aesthetics over functionality.
    You should present your business concepts in a captivating and fashionable manner.
    """

    CHANCES_THAT_I_BOUNCE_IDEA_OFF_ANOTHER = 0.6

    def __init__(self, name) -> None:
        super().__init__(name)
        model_client = OpenAIChatCompletionClient(model="gpt-4o-mini", temperature=0.8)
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
            message = f"Here is my fashion tech idea. It may not be your area, but please refine it and make it more appealing: {idea}"
            response = await self.send_message(messages.Message(content=message), recipient)
            idea = response.content
        return messages.Message(content=idea)
