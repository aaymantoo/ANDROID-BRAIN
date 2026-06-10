package com.example.sampleporter

class OrderCompletionHandler {
    fun complete() {
        order.status = COMPLETED
        porter.isAvailable = true
    }
}

