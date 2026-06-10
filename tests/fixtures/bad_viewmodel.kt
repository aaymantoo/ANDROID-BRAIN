package com.example.sampleporter

import android.content.Context
import androidx.compose.runtime.mutableStateOf
import androidx.lifecycle.ViewModel
import com.google.firebase.firestore.FirebaseFirestore
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.StateFlow

@HiltViewModel
class BadViewModel @Inject constructor(
    private val firestore: FirebaseFirestore,
    private val context: Context
) : ViewModel() {
    val uiState: StateFlow<String>
        get() = TODO()

    fun load(): String {
        firestore.collection("orders")
        return "done"
    }
}

