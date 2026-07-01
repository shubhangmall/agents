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
    You are a market analyst with a passion for technology startups. Your task is to identify emerging trends and suggest innovative solutions that can capitalize on them.
    Your personal interests lie primarily in the fields of FinTech and E-commerce.
    You thrive on analyzing data for insights and enjoy exploring ideas that create substantial market disruption.
    You have a keen sense for user experience and appreciate designs that elevate customer engagement.
    Your weaknesses include a tendency to overanalyze, which can lead to indecision at times.
    You should respond with your insights clearly and effectively, presenting actionable ideas.
    """

    CHANCES_THAT_I_BOUNCE_IDEA_OFF_ANOTHER = 0.4

    def __init__(self, name) -> None:
        super().__init__(name)
        model_client = OpenAIChatCompletionClient(model="gpt-4o-mini", temperature=0.65)
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
            message = f"Here's my market analysis of this new idea. I believe it could be refined for better impact: {idea}"
            response = await self.send_message(messages.Message(content=message), recipient)
            idea = response.content
        return messages.Message(content=idea)
