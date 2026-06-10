"""
Creates an enriched brain JSON for bigbaagh auth feature,
exactly as Phase 0B would produce from the hyperspec PRD.
This simulates the LLM-enriched output (no API key needed for testing).
"""

from __future__ import annotations

import json
from pathlib import Path

from project_brain.brain.schema import (
    BusinessRule,
    DataField,
    DataModel,
    DataSource,
    EventSpec,
    FirestoreCollection,
    FirestoreSchema,
    Meta,
    NavigationGraph,
    NavigationRoute,
    Phase,
    ProjectBrain,
    Repository,
    RepositoryMethod,
    Screen,
    StateField,
    StateMachine,
    StateTransition,
    UserRole,
    ViewModel,
    ViewModelFunction,
)
from project_brain.brain.manager import BrainManager


def build_enriched_auth_brain() -> ProjectBrain:
    return ProjectBrain(
        meta=Meta(
            project_name="BigBaagh Auth",
            entry_point="prd",
            architecture="MVVM+Hilt+Compose+Firebase",
            package_name="com.bigbaagh.app",
            min_sdk=26,
            target_sdk=35,
        ),
        user_roles=[
            UserRole(id="customer", name="Customer", description="Authenticates via phone OTP", app_module="app"),
        ],
        data_models=[
            DataModel(
                id="PhoneEntryUiState",
                fields=[
                    DataField(name="phoneNumber", type="String"),
                    DataField(name="phoneNumberError", type="String", nullable=True),
                    DataField(name="errorMessage", type="String", nullable=True),
                    DataField(name="isOfflineMode", type="Boolean"),
                    DataField(name="isSendingOtp", type="Boolean"),
                ],
            ),
            DataModel(
                id="OtpUiState",
                fields=[
                    DataField(name="phoneNumber", type="String"),
                    DataField(name="digits", type="List<String>"),
                    DataField(name="resendSecondsRemaining", type="Int"),
                    DataField(name="isVerifying", type="Boolean"),
                    DataField(name="isResending", type="Boolean"),
                    DataField(name="errorMessage", type="String", nullable=True),
                    DataField(name="isOfflineMode", type="Boolean"),
                ],
            ),
            DataModel(
                id="User",
                fields=[
                    DataField(name="uid", type="String"),
                    DataField(name="phoneNumber", type="String", nullable=True),
                    DataField(name="name", type="String", nullable=True),
                    DataField(name="isProfileComplete", type="Boolean"),
                ],
                firestore_collection="/users/{uid}",
            ),
        ],
        viewmodels=[
            ViewModel(
                id="PhoneEntryViewModel",
                screen="PhoneEntryScreen",
                repository="AuthRepository",
                use_cases=["SendOtpUseCase"],
                inject_dependencies=["SendOtpUseCase"],
                ui_state_class="PhoneEntryUiState",
                ui_state_type="data_class",
                event_class="PhoneEntryUiEffect",
                has_mutex=False,
                has_saved_state=False,
                state_fields=[
                    StateField(name="phoneNumber", type="String", default='""'),
                    StateField(name="phoneNumberError", type="String", nullable=True, default="null"),
                    StateField(name="errorMessage", type="String", nullable=True, default="null"),
                    StateField(name="isOfflineMode", type="Boolean", default="false"),
                    StateField(name="isSendingOtp", type="Boolean", default="false"),
                ],
                events=[
                    EventSpec(name="NavigateToOtp", has_data=True, data="val phoneNumber: String"),
                ],
                functions=[
                    ViewModelFunction(
                        name="onPhoneNumberChanged",
                        params=["phoneNumber: String"],
                        returns="Unit",
                        business_rule="Normalise: strip non-digits, max 10 chars. Inline-validate with validateIndianPhoneNumber.",
                        state_updates=["phoneNumber", "phoneNumberError", "errorMessage"],
                        events_fired=[],
                        concurrent=False,
                    ),
                    ViewModelFunction(
                        name="onSendOtpClicked",
                        params=[],
                        returns="Unit",
                        business_rule="BR001: Validate phone via validateIndianPhoneNumber before sending. On Invalid → set phoneNumberError. On Valid → call sendOtp.",
                        state_updates=["isSendingOtp", "phoneNumberError", "errorMessage"],
                        events_fired=["NavigateToOtp"],
                        concurrent=False,
                    ),
                    ViewModelFunction(
                        name="retrySendOtp",
                        params=[],
                        returns="Unit",
                        business_rule="Delegates to onSendOtpClicked for retry.",
                        state_updates=[],
                        events_fired=["NavigateToOtp"],
                        concurrent=False,
                    ),
                ],
            ),
            ViewModel(
                id="OtpViewModel",
                screen="OtpVerificationScreen",
                repository="AuthRepository",
                use_cases=["VerifyOtpUseCase", "SendOtpUseCase"],
                inject_dependencies=["VerifyOtpUseCase", "SendOtpUseCase"],
                ui_state_class="OtpUiState",
                ui_state_type="data_class",
                event_class="OtpUiEffect",
                has_mutex=False,
                has_saved_state=True,
                state_fields=[
                    StateField(name="phoneNumber", type="String", default='""'),
                    StateField(name="digits", type="List<String>", default='List(6) { "" }'),
                    StateField(name="resendSecondsRemaining", type="Int", default="60"),
                    StateField(name="isVerifying", type="Boolean", default="false"),
                    StateField(name="isResending", type="Boolean", default="false"),
                    StateField(name="errorMessage", type="String", nullable=True, default="null"),
                    StateField(name="isOfflineMode", type="Boolean", default="false"),
                ],
                events=[
                    EventSpec(name="NavigateToHome", has_data=False),
                    EventSpec(name="NavigateToProfileSetup", has_data=False),
                ],
                functions=[
                    ViewModelFunction(
                        name="onOtpChanged",
                        params=["digits: List<String>"],
                        returns="Unit",
                        business_rule="Sanitise digits: strip non-digits, max 1 char per slot, pad/truncate to OTP_LENGTH=6.",
                        state_updates=["digits", "errorMessage"],
                        events_fired=[],
                        concurrent=False,
                    ),
                    ViewModelFunction(
                        name="onVerifyClicked",
                        params=[],
                        returns="Unit",
                        business_rule="BR002: Guard with canVerify (all 6 digits filled, not already verifying). On success: emit NavigateToHome or NavigateToProfileSetup based on user.isProfileComplete.",
                        state_updates=["isVerifying", "errorMessage"],
                        events_fired=["NavigateToHome", "NavigateToProfileSetup"],
                        concurrent=False,
                    ),
                    ViewModelFunction(
                        name="onResendClicked",
                        params=[],
                        returns="Unit",
                        business_rule="BR003: Guard with canResend (resendSecondsRemaining == 0, not resending, not verifying). On success: restart countdown.",
                        state_updates=["isResending", "errorMessage"],
                        events_fired=[],
                        concurrent=False,
                    ),
                    ViewModelFunction(
                        name="retryLastAction",
                        params=[],
                        returns="Unit",
                        business_rule="Retry last failed action (Resend or Verify). No-op if no failure recorded.",
                        state_updates=[],
                        events_fired=[],
                        concurrent=False,
                    ),
                ],
            ),
        ],
        repositories=[
            Repository(
                id="AuthRepository",
                interface="AuthRepository",
                implementation="AuthRepositoryImpl",
                data_sources=["FirebaseAuth", "FirebaseFirestore", "DataStore<Preferences>"],
                typed_data_sources=[
                    DataSource(
                        param_name="firebaseAuth",
                        type="FirebaseAuth",
                        import_path="com.google.firebase.auth.FirebaseAuth",
                    ),
                    DataSource(
                        param_name="firestore",
                        type="FirebaseFirestore",
                        import_path="com.google.firebase.firestore.FirebaseFirestore",
                    ),
                    DataSource(
                        param_name="dataStore",
                        type="DataStore<Preferences>",
                        import_path="androidx.datastore.core.DataStore",
                    ),
                ],
                methods=[
                    RepositoryMethod(
                        name="observeAuthState",
                        params=[],
                        is_flow=True,
                        flow_type="AppResult<User?>",
                    ),
                    RepositoryMethod(
                        name="sendOtp",
                        params=["phoneNumber: String"],
                        result_wrapped=True,
                        result_type="Unit",
                    ),
                    RepositoryMethod(
                        name="verifyOtp",
                        params=["phoneNumber: String", "otp: String"],
                        result_wrapped=True,
                        result_type="User",
                    ),
                    RepositoryMethod(
                        name="completeProfileSetup",
                        params=["name: String", "email: String = \"\""],
                        result_wrapped=True,
                        result_type="User",
                    ),
                ],
            ),
        ],
        screens=[
            Screen(
                id="PhoneEntryScreen",
                route="auth/phone",
                phase=1,
                status="pending",
                viewmodel="PhoneEntryViewModel",
                repository="AuthRepository",
                use_cases=["SendOtpUseCase"],
                models=["PhoneEntryUiState"],
                ui_states=["isSendingOtp", "errorMessage"],
            ),
            Screen(
                id="OtpVerificationScreen",
                route="auth/otp/{phone}",
                phase=1,
                status="pending",
                viewmodel="OtpViewModel",
                repository="AuthRepository",
                use_cases=["VerifyOtpUseCase", "SendOtpUseCase"],
                models=["OtpUiState"],
                nav_args=["phone: String"],
                ui_states=["isVerifying", "isResending", "resendSecondsRemaining"],
            ),
        ],
        state_machines=[
            StateMachine(
                entity="AuthState",
                states=["Unauthenticated", "Authenticated"],
                transitions=[
                    StateTransition(**{"from": "Unauthenticated", "to": "Authenticated"}),
                    StateTransition(**{"from": "Authenticated", "to": "Unauthenticated"}),
                ],
            ),
        ],
        firestore_schema=FirestoreSchema(
            collections=[
                FirestoreCollection(
                    path="/users/{uid}",
                    fields=["uid", "phoneNumber", "name", "isProfileComplete", "createdAt"],
                    consistency_rules=["phoneNumber must be set when auth method is phone"],
                ),
            ],
        ),
        business_rules=[
            BusinessRule(
                id="BR001",
                description="Phone number must pass validateIndianPhoneNumber before OTP is sent. On invalid input, set phoneNumberError inline; do not call Firebase.",
                trigger="onSendOtpClicked",
                enforcement="ViewModel",
            ),
            BusinessRule(
                id="BR002",
                description="OTP verification must check canVerify state guard (all 6 digits, not already verifying) before calling use case.",
                trigger="onVerifyClicked",
                enforcement="ViewModel",
            ),
            BusinessRule(
                id="BR003",
                description="Resend OTP is rate-limited by countdown timer. canResend requires resendSecondsRemaining == 0 and not currently resending or verifying.",
                trigger="onResendClicked",
                enforcement="ViewModel",
            ),
            BusinessRule(
                id="BR004",
                description="After successful OTP verification, navigate to ProfileSetup if user.isProfileComplete is false, else navigate to Home.",
                trigger="verifyOtp success",
                enforcement="ViewModel",
            ),
        ],
        navigation_graph=NavigationGraph(
            start_destination="PhoneEntryScreen",
            routes=[
                NavigationRoute(id="PhoneEntryScreen", screen="PhoneEntryScreen", next=["OtpVerificationScreen"]),
                NavigationRoute(id="OtpVerificationScreen", screen="OtpVerificationScreen", next=["HomeScreen", "ProfileSetupScreen"]),
            ],
        ),
        phases=[
            Phase(
                number=1,
                name="Phone OTP Auth",
                status="pending",
                screens=["PhoneEntryScreen", "OtpVerificationScreen"],
                completion_criteria=["Phone OTP flow works end-to-end", "No CLASS_A violations"],
            ),
        ],
    )


def main():
    brain = build_enriched_auth_brain()
    output_path = Path("bigbaagh_auth_enriched_brain.json")
    BrainManager(output_path).save(brain)
    print(f"Brain written to: {output_path}")
    print(json.dumps(brain.summary(), indent=2))


if __name__ == "__main__":
    main()
