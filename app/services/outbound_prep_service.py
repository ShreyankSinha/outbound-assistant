from __future__ import annotations

from pydantic import BaseModel

from app.llm.instruction_parser import OperatorInstructionParser
from app.schemas.customer import CustomerRecord
from app.schemas.parsed_intent import ParsedIntent
from app.schemas.session_state import SessionState
from app.services.customer_directory import CustomerDirectory
from app.services.session_service import SessionService


class PreparedCall(BaseModel):
    operator_instruction: str
    parsed_intent: ParsedIntent
    customer_record: CustomerRecord
    personalized_message: str
    session: SessionState | None = None
    telephony_attempted: bool = False
    telephony_error: str | None = None


class OutboundPrepService:
    def __init__(
        self,
        directory: CustomerDirectory,
        session_service: SessionService,
        parser: OperatorInstructionParser | None = None,
    ) -> None:
        self.directory = directory
        self.session_service = session_service
        self.parser = parser or OperatorInstructionParser()

    async def prepare_from_instruction(self, instruction: str) -> PreparedCall:
        parsed_intent = await self.parser.parse(instruction)
        if parsed_intent.customer_id is None:
            raise ValueError("Operator instruction did not include a customer ID.")

        customer = self.directory.get_customer_by_id(parsed_intent.customer_id)
        if customer is None:
            raise ValueError(f"No customer found for customer_id={parsed_intent.customer_id}.")

        parsed_intent.customer_name = parsed_intent.customer_name or customer.customer_name
        parsed_intent.phone_number = customer.phone_number
        message = self._build_personalized_message(parsed_intent, customer)

        return PreparedCall(
            operator_instruction=instruction,
            parsed_intent=parsed_intent,
            customer_record=customer,
            personalized_message=message,
        )

    async def attempt_call_from_instruction(self, instruction: str) -> PreparedCall:
        prepared = await self.prepare_from_instruction(instruction)
        session = await self.session_service.create_session(
            operator_instruction=instruction,
            call_target=prepared.customer_record.phone_number,
        )
        session.parsed_intent = prepared.parsed_intent
        session.agent_last_message = prepared.personalized_message

        try:
            session = await self.session_service.start_session(session)
            prepared.telephony_attempted = True
            prepared.session = session
        except Exception as exc:
            prepared.telephony_attempted = True
            prepared.telephony_error = str(exc)
            prepared.session = session
        return prepared

    @staticmethod
    def _build_personalized_message(parsed_intent: ParsedIntent, customer: CustomerRecord) -> str:
        amount = f" of {parsed_intent.amount}" if parsed_intent.amount else ""
        reason = parsed_intent.issue_type.replace("_", " ")
        return (
            f"Hello {customer.customer_name}, this is a follow-up call regarding your {reason}{amount}. "
            f"We're calling to {parsed_intent.desired_resolution}. Please let us know how you'd like to proceed."
        )
