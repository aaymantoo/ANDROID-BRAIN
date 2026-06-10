# PRD: [Project Name]

## Document Control

- Version: 1.0
- Owner: [Name]
- Last Updated: [Date]

## 1. Project Overview

Describe the Android app, audience, architecture, package name, min SDK, and target SDK.

## 2. User Roles

| id | name | description | app_module |
|---|---|---|---|
| customer | Customer | Books service | customer |

## 3. Features & Screens

### Feature: [Feature Name]

- Screen: HomeScreen
- Route: home
- ViewModel: HomeViewModel
- Repository: HomeRepository
- UI states: Loading, Content, Error

## 4. Data Models

### Order

| name | type | nullable |
|---|---|---|
| id | String | false |
| status | String | false |

## 5. State Machines

### Order States

- States: PENDING, ASSIGNED, COMPLETED, CANCELLED
- Transition: PENDING -> ASSIGNED
- Transition: ASSIGNED -> COMPLETED

## 6. Firestore Schema

### Collection: /orders/{orderId}

- Fields: id, status, createdAt
- Consistency rule: status must match Order.status

## 7. Business Rules

- BR001: When Order.status becomes COMPLETED, all linked availability fields must update.

## 8. Navigation Flow

- HomeScreen -> OrderTrackingScreen

## 9. Phase Breakdown

### Phase 1: Core

- Screens: HomeScreen
- Completion criteria: all screens generated, no CLASS_A violations

## 10. Cloud Functions

List required Cloud Functions or write "None".

## 11. Known Risks

List known product or architecture risks.

