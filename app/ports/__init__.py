"""Port interfaces to the client systems (architecture rule 2).

Each port is a Protocol; mocks (mocks/) and real adapters (app/adapters/)
implement the same contract, so swapping a mock for a real adapter is
configuration, not code.
"""

from app.ports.errors import (
    PortAuthError,
    PortError,
    PortProtocolError,
    PortRateLimitedError,
    PortTransientError,
    PortValidationError,
)
from app.ports.hiredesk import (
    ApplicationCreate,
    CandidateCreate,
    HireDeskCandidateMergedError,
    HireDeskPort,
    HireDeskRequisitionClosedError,
    RequisitionCreate,
    StageEvent,
    StageUpdate,
)
from app.ports.learnbite import EnrollmentCreate, EnrollmentStatus, LearnBitePort
from app.ports.m365 import (
    CalendarSlot,
    DocumentRequestEmail,
    InterviewEvent,
    M365Port,
    ManagerCalendar,
)
from app.ports.messaging import InboundMessage, MessagingChannelPort, OutboundMessage
from app.ports.nomina360 import (
    CsvSnapshot,
    EmployeeCreate,
    EmployeeCsvRow,
    Nomina360Body,
    Nomina360Port,
    Nomina360ValidationError,
    PendingWrite,
    ReconciliationReport,
    ReconciliationTask,
)
from app.ports.shiftgrid import (
    OpenShiftRead,
    RotaAssignment,
    RotaView,
    ShiftAssign,
    ShiftGridPort,
    ShiftGridShift,
    ShiftGridShiftFilledError,
    ShiftRelease,
)

__all__ = [
    "ApplicationCreate",
    "CalendarSlot",
    "CandidateCreate",
    "CsvSnapshot",
    "DocumentRequestEmail",
    "EmployeeCreate",
    "EmployeeCsvRow",
    "EnrollmentCreate",
    "EnrollmentStatus",
    "HireDeskCandidateMergedError",
    "HireDeskPort",
    "HireDeskRequisitionClosedError",
    "InboundMessage",
    "InterviewEvent",
    "LearnBitePort",
    "M365Port",
    "ManagerCalendar",
    "MessagingChannelPort",
    "Nomina360Body",
    "Nomina360Port",
    "Nomina360ValidationError",
    "OpenShiftRead",
    "OutboundMessage",
    "PendingWrite",
    "PortAuthError",
    "PortError",
    "PortProtocolError",
    "PortRateLimitedError",
    "PortTransientError",
    "PortValidationError",
    "ReconciliationReport",
    "ReconciliationTask",
    "RequisitionCreate",
    "RotaAssignment",
    "RotaView",
    "ShiftAssign",
    "ShiftGridPort",
    "ShiftGridShift",
    "ShiftGridShiftFilledError",
    "ShiftRelease",
    "StageEvent",
    "StageUpdate",
]
