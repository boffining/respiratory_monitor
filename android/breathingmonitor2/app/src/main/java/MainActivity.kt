package com.example.breathingmonitor

import android.graphics.BitmapFactory
import android.graphics.Color
import android.os.Bundle
import android.util.Log
import android.view.View
import android.widget.ImageView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.github.mikephil.charting.charts.LineChart
import com.github.mikephil.charting.components.YAxis
import com.github.mikephil.charting.data.Entry
import com.github.mikephil.charting.data.LineData
import com.github.mikephil.charting.data.LineDataSet
import org.json.JSONObject
import java.io.DataInputStream
import java.io.InputStream
import java.net.Socket
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.concurrent.thread

class MainActivity : AppCompatActivity() {
    private lateinit var videoView: ImageView
    private lateinit var breathingRateTextView: TextView
    private lateinit var breathingStatusTextView: TextView
    private lateinit var breathingChart: LineChart
    private val entries = ArrayList<Entry>()
    private val maxDataPoints = 200
    private var lastFrameTime = 0L
    private var frameCount = 0
    private var fps = 0f
    private var isConnected = false

    // Server configuration
    private val serverIP = "192.168.50.175" // Replace with your server's IP
    private val videoPort = 9999
    private val dataPort = 32345

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        videoView = findViewById(R.id.videoView)
        breathingRateTextView = findViewById(R.id.breathingRateTextView)
        breathingStatusTextView = findViewById(R.id.breathingStatusTextView)
        breathingChart = findViewById(R.id.breathingChart)
        
        setupChart()
        
        // Start connection threads
        startVideoStreamThread()
        startBreathingDataThread()
        
        // Start FPS counter
        startFpsCounter()
    }

    private fun setupChart() {
        breathingChart.apply {
            description.isEnabled = false
            setTouchEnabled(false)
            isDragEnabled = false
            setScaleEnabled(false)
            setDrawGridBackground(false)
            
            // Configure X axis
            xAxis.setDrawGridLines(false)
            xAxis.setDrawAxisLine(true)
            xAxis.textColor = Color.WHITE
            
            // Configure Y axis
            axisLeft.setDrawGridLines(true)
            axisLeft.gridColor = Color.argb(50, 255, 255, 255)
            axisLeft.textColor = Color.WHITE
            axisLeft.setDrawAxisLine(true)
            axisRight.isEnabled = false
            
            // Disable legend
            legend.isEnabled = false
            
            // Set animation
            animateX(500)
            
            // Create empty dataset
            val dataSet = LineDataSet(entries, "Breathing").apply {
                color = Color.GREEN
                setDrawCircles(false)
                setDrawValues(false)
                mode = LineDataSet.Mode.CUBIC_BEZIER
                lineWidth = 3f
                setDrawFilled(true)
                fillColor = Color.argb(80, 0, 255, 0)
                fillAlpha = 80
                axisDependency = YAxis.AxisDependency.LEFT
            }
            
            data = LineData(dataSet)
        }
    }

    private fun startFpsCounter() {
        thread {
            while (true) {
                Thread.sleep(1000)
                runOnUiThread {
                    if (isConnected) {
                        val statusText = "FPS: $fps | Connected to $serverIP"
                        breathingRateTextView.text = statusText
                    }
                }
                fps = frameCount.toFloat()
                frameCount = 0
            }
        }
    }

    private fun startVideoStreamThread() {
        thread {
            while (true) {
                try {
                    Log.d("VideoStream", "Connecting to video server at $serverIP:$videoPort")
                    val videoSocket = Socket(serverIP, videoPort)
                    val videoInputStream: InputStream = videoSocket.getInputStream()
                    
                    runOnUiThread {
                        isConnected = true
                        breathingRateTextView.text = "Connected to video stream"
                    }

                    val sizeBuffer = ByteArray(4)
                    
                    while (true) {
                        // Read frame size (4 bytes, big endian)
                        var bytesRead = 0
                        while (bytesRead < 4) {
                            val read = videoInputStream.read(sizeBuffer, bytesRead, 4 - bytesRead)
                            if (read == -1) throw Exception("End of stream")
                            bytesRead += read
                        }
                        
                        val size = ByteBuffer.wrap(sizeBuffer).order(ByteOrder.BIG_ENDIAN).int
                        if (size <= 0 || size > 10_000_000) {  // Sanity check
                            Log.e("VideoStream", "Invalid frame size: $size")
                            continue
                        }

                        // Read frame data
                        val frameBuffer = ByteArray(size)
                        bytesRead = 0
                        while (bytesRead < size) {
                            val read = videoInputStream.read(frameBuffer, bytesRead, size - bytesRead)
                            if (read == -1) throw Exception("End of stream")
                            bytesRead += read
                        }

                        // Decode and display frame
                        val bitmap = BitmapFactory.decodeByteArray(frameBuffer, 0, size)
                        if (bitmap != null) {
                            runOnUiThread {
                                videoView.setImageBitmap(bitmap)
                                frameCount++
                            }
                        }
                    }
                } catch (e: Exception) {
                    Log.e("VideoStream", "Error in video stream: ${e.message}")
                    e.printStackTrace()
                    runOnUiThread {
                        isConnected = false
                        breathingRateTextView.text = "Video Error: ${e.localizedMessage}"
                    }
                    
                    // Wait before reconnecting
                    Thread.sleep(3000)
                }
            }
        }
    }

    private fun startBreathingDataThread() {
        thread {
            while (true) {
                try {
                    Log.d("BreathingData", "Connecting to data server at $serverIP:$dataPort")
                    val dataSocket = Socket(serverIP, dataPort)
                    val dataInput = DataInputStream(dataSocket.getInputStream())
                    
                    val sizeBuffer = ByteArray(4)
                    
                    while (true) {
                        // Read data size (4 bytes)
                        dataInput.readFully(sizeBuffer)
                        val dataSize = ByteBuffer.wrap(sizeBuffer).order(ByteOrder.BIG_ENDIAN).int
                        
                        if (dataSize <= 0 || dataSize > 1_000_000) {  // Sanity check
                            Log.e("BreathingData", "Invalid data size: $dataSize")
                            continue
                        }
                        
                        // Read JSON data
                        val dataBuffer = ByteArray(dataSize)
                        dataInput.readFully(dataBuffer)
                        
                        val jsonData = String(dataBuffer, Charsets.UTF_8)
                        processBreathingData(jsonData)
                    }
                } catch (e: Exception) {
                    Log.e("BreathingData", "Error in breathing data stream: ${e.message}")
                    e.printStackTrace()
                    runOnUiThread {
                        breathingStatusTextView.text = "Data Error: ${e.localizedMessage}"
                    }
                    
                    // Wait before reconnecting
                    Thread.sleep(3000)
                }
            }
        }
    }
    
    private fun processBreathingData(jsonData: String) {
        try {
            val data = JSONObject(jsonData)
            val motionState = data.getString("motion_state")
            val alert = data.getString("alert")
            val waveformArray = data.getJSONArray("waveform")
            
            // Update UI with status
            runOnUiThread {
                breathingStatusTextView.text = "$motionState | $alert"
                
                // Set text color based on alert status
                if (alert != "Normal") {
                    breathingStatusTextView.setTextColor(Color.RED)
                } else {
                    breathingStatusTextView.setTextColor(Color.WHITE)
                }
            }
            
            // Process waveform data
            val waveformValues = FloatArray(waveformArray.length())
            for (i in 0 until waveformArray.length()) {
                waveformValues[i] = waveformArray.getDouble(i).toFloat()
            }
            
            // Update chart with new data
            updateChart(waveformValues)
            
        } catch (e: Exception) {
            Log.e("BreathingData", "Error processing breathing data: ${e.message}")
        }
    }

    private fun updateChart(values: FloatArray) {
        runOnUiThread {
            // Clear old entries if we're getting a full waveform
            if (values.size > 10) {
                entries.clear()
                
                // Add all new values
                for (i in values.indices) {
                    entries.add(Entry(i.toFloat(), values[i]))
                }
            } else {
                // Add new values and remove old ones to maintain max size
                for (value in values) {
                    if (entries.size >= maxDataPoints) {
                        entries.removeAt(0)
                    }
                    entries.add(Entry(entries.size.toFloat(), value))
                }
            }
            
            // Update chart
            val dataSet = breathingChart.data.getDataSetByIndex(0) as LineDataSet
            dataSet.values = entries
            
            breathingChart.data.notifyDataChanged()
            breathingChart.notifyDataSetChanged()
            breathingChart.setVisibleXRange(0f, maxDataPoints.toFloat())
            breathingChart.moveViewToX(entries.size.toFloat())
            breathingChart.invalidate()
        }
    }
}
