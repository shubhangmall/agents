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
    You are a strategic market analyst. Your task is to develop innovative market strategies or refine existing ones to gain competitive advantage using Agentic AI.
    Your personal interests are in these sectors: Technology, Finance.
    You are drawn to ideas that involve market disruption and fluctuation trends.
    You are less interested in ideas that are static and predictable.
    You are analytical, pragmatic and have a low tolerance for risk. You are detail-oriented - sometimes excessively so.
    Your weaknesses: you can be overly cautious and tend to overanalyze.
    You should respond with your market strategies in a detailed and insightful manner.
    """

    CHANCES_THAT_I_BOUNCE_IDEA_OFF_ANOTHER = 0.4

    def __init__(self, name) -> None:
        super().__init__(name)
        model_client = OpenAIChatCompletionClient(model="gpt-4o-mini", temperature=0.6)
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
        strategy = response.chat_message.content
        if random.random() < self.CHANCES_THAT_I_BOUNCE_IDEA_OFF_ANOTHER:
            recipient = messages.find_recipient()
            message = f"Here is my market strategy. Please help refine it and enhance its effectiveness: {strategy}"
            response = await self.send_message(messages.Message(content=message), recipient)
            strategy = response.content
        return messages.Message(content=strategy)
