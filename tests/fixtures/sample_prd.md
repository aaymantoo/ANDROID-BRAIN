# PRD: Sample Porter

## 1. Project Overview

Package name: com.example.sampleporter
Min SDK: 26
Target SDK: 35

## 2. User Roles

| id | name | description | app_module |
|---|---|---|---|
| customer | Customer | Books delivery | customer |
| porter | Porter | Fulfills delivery | porter |

## 3. Features & Screens

### Feature: Orders

- Screen: HomeScreen
- Route: home
- ViewModel: HomeViewModel
- Repository: OrderRepository
- UI states: Loading, Active, Error
- Screen: OrderTrackingScreen
- Route: order_tracking/{orderId}
- ViewModel: OrderTrackingViewModel
- Repository: OrderRepository

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

- BR001: When Order.status becomes COMPLETED, porter availability must update.

## 8. Navigation Flow

- HomeScreen -> OrderTrackingScreen

## 9. Phase Breakdown

### Phase 1: Core Orders

- Screens: HomeScreen, OrderTrackingScreen
- Completion criteria: all screens generated, no CLASS_A violations

