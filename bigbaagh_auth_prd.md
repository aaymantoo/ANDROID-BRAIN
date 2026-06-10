# PRD: BigBaagh Auth

## 1. Project Overview

Package name: com.bigbaagh.app
Min SDK: 26
Target SDK: 35
Architecture: MVVM+Hilt+Compose+Firebase

## 2. User Roles

| id | name | description | app_module |
|---|---|---|---|
| customer | Customer | Authenticates via phone OTP | app |
| admin | Admin | Authenticates via email/password fallback | app |

## 3. Features & Screens

### Feature: Auth

- Screen: PhoneInputScreen
- Route: auth/phone
- ViewModel: AuthViewModel
- Repository: AuthRepository
- Use Cases: RequestOtpUseCase
- UI states: Idle, Loading, Error

- Screen: OtpVerificationScreen
- Route: auth/otp
- ViewModel: AuthViewModel
- Repository: AuthRepository
- Use Cases: VerifyOtpUseCase, ResendOtpUseCase
- UI states: Ready, Cooldown, Verifying, Resending

- Screen: EmailAuthScreen
- Route: auth/email
- ViewModel: EmailAuthViewModel
- Repository: AuthRepository
- Use Cases: LoginWithEmailUseCase
- UI states: Idle, Loading, Error

## 4. Data Models

### AuthUser

| name | type | nullable |
|---|---|---|
| uid | String | false |
| phoneNumber | String | true |
| email | String | true |
| fcmToken | String | true |

### OtpSession

| name | type | nullable |
|---|---|---|
| pendingPhone | String | true |
| lastRequestTime | Long | false |

## 5. State Machines

### AuthState

- States: Loading, Unauthenticated, Authenticated
- Transition: Unauthenticated -> Authenticated
- Transition: Authenticated -> Unauthenticated

### OtpFlow

- States: Idle, OtpRequested, OtpVerified
- Transition: Idle -> OtpRequested
- Transition: OtpRequested -> OtpVerified

## 6. Firestore Schema

### Collection: /users/{uid}

- Fields: uid, phoneNumber, email, fcmToken, createdAt
- Consistency rule: phoneNumber must be set when auth method is phone

## 7. Business Rules

- BR001: OTP resend is rate-limited to a 30-second cooldown. Calling resendOtp before cooldown ends must throw ResendTooSoonException.
- BR002: verifyOtp must be guarded by a mutex to prevent duplicate concurrent calls.
- BR003: After successful OTP verification, ensureUserDocument must write the user record to Firestore.
- BR004: Pending phone number must be persisted to DataStore before OTP verification so the session survives process death.
- BR005: On logout, local user data must be cleared before signing out of Firebase.

## 8. Navigation Flow

- PhoneInputScreen -> OtpVerificationScreen
- OtpVerificationScreen -> HomeScreen

## 9. Phase Breakdown

### Phase 1: Phone OTP Auth

- Screens: PhoneInputScreen, OtpVerificationScreen
- Completion criteria: phone OTP flow works end to end, no CLASS_A violations

### Phase 2: Email Fallback Auth

- Screens: EmailAuthScreen
- Completion criteria: email login works, parity with phone flow
