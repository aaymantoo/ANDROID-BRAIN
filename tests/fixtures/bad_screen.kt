package com.example.sampleporter

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import com.google.firebase.firestore.FirebaseFirestore

@Composable
fun BadScreen() {
    FirebaseFirestore.getInstance().collection("orders")
    Text("Hardcoded")
}

