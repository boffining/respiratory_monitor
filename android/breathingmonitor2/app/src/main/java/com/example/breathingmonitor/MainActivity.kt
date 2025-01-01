package com.example.breathingmonitor

import android.os.Bundle
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.Socket
import kotlin.concurrent.thread

class MainActivity : AppCompatActivity() {
    private lateinit var breathingStatusTextView: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        breathingStatusTextView = findViewById(R.id.breathingRateTextView)

        thread {
            try {
                val serverIP = "192.168.50.175" // Replace with your server's IP
                val serverPort = 32345
                val socket = Socket(serverIP, serverPort)

                val reader = BufferedReader(InputStreamReader(socket.getInputStream()))
                while (true) {
                    val statusMessage = reader.readLine() // Read the clean message
                    runOnUiThread {
                        breathingStatusTextView.text = statusMessage // Display directly
                    }
                }
            } catch (e: Exception) {
                e.printStackTrace()
                runOnUiThread {
                    breathingStatusTextView.text = "Error: ${e.localizedMessage}"
                }
            }
        }
    }
}