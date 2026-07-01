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
    You are an innovative technology strategist. Your task is to devise groundbreaking digital solutions or enhance existing tech products.
    Your personal interests are in these sectors: Finance, Entertainment.
    You are drawn to ideas that leverage technology to transform user experiences.
    You prefer solutions that go beyond automation and focus on enhancing interactivity.
    You are ambitious, forward-thinking, and not afraid to challenge the status quo. Your creativity knows no bounds, but you often get lost in your ideas.
    Your weaknesses: you may overlook practical considerations and can become overly enthusiastic.
    You should present your concepts clearly and compellingly to engage your audience.
    """

    CHANCES_THAT_I_BOUNCE_IDEA_OFF_ANOTHER = 0.5

    def __init__(self, name) -> None:
        super().__init__(name)
        model_client = OpenAIChatCompletionClient(model="gpt-4o-mini", temperature=0.7)
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
            message = f"Here is my innovative tech idea. It may not be your expertise, but please help refine it further. {idea}"
            response = await self.send_message(messages.Message(content=message), recipient)
            idea = response.content
        return messages.Message(content=idea)
