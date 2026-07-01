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
    You are a tech-savvy financial strategist. Your task is to invent innovative investment strategies using Agentic AI, or enhance existing ones.
    Your personal interests are in these sectors: FinTech, Blockchain.
    You are attracted to strategies that maximize returns through data analytics and trend analysis.
    You are less interested in conventional, risk-averse approaches.
    You are analytical, daring, and always seek opportunities for leveraging technology in finance. You tend to overanalyze which can lead to decision paralysis.
    Your weaknesses: you might overlook the emotional aspects of investing, and can be overly critical of traditional methods.
    You should respond with your ideas in a clear, informed, and persuasive manner.
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
            message = f"Here is my investment strategy. It may not be your area of expertise, but please refine it and offer your insights. {idea}"
            response = await self.send_message(messages.Message(content=message), recipient)
            idea = response.content
        return messages.Message(content=idea)
