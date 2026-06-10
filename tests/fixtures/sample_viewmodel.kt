package com.example.sampleporter

import androidx.lifecycle.ViewModel
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.StateFlow

@HiltViewModel
class OrderTrackingViewModel @Inject constructor(
    private val orderRepository: OrderRepository,
    private val getOrderUseCase: GetOrderUseCase
) : ViewModel() {
    val uiState: StateFlow<OrderTrackingUiState>
        get() = TODO()
}

