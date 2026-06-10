package com.example.sampleporter

interface OrderRepository

class OrderRepositoryImpl : OrderRepository {
    fun listen() = firestore.collection("orders")
}

data class Order(
    val id: String,
    val status: String,
)
