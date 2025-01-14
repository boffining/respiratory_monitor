package com.example.breathingmonitor

import android.graphics.BitmapFactory
import android.graphics.Color
import android.os.Bundle
import android.widget.ImageView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.github.mikephil.charting.charts.LineChart
import com.github.mikephil.charting.data.Entry
import com.github.mikephil.charting.data.LineData
import com.github.mikephil.charting.data.LineDataSet
import java.io.BufferedReader
import java.io.DataInputStream
import java.io.InputStream
import java.io.InputStreamReader
import java.net.Socket
import kotlin.concurrent.thread

class MainActivity : AppCompatActivity() {
    private lateinit var videoView: ImageView
    private lateinit var breathingRateTextView: TextView
    private lateinit var breathingChart: LineChart
    private val entries = ArrayList<Entry>()
    private val maxDataPoints = 100

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        videoView = findViewById(R.id.videoView)
        breathingRateTextView = findViewById(R.id.breathingRateTextView)
        breathingChart = findViewById(R.id.breathingChart)
        
        setupChart()
        startVideoStreamThread()
        startBreathingDataThread()
    }

    private fun setupChart() {
        breathingChart.apply {
            description.isEnabled = false
            setTouchEnabled(false)
            isDragEnabled = false
            setScaleEnabled(false)
            setDrawGridBackground(false)
            
            xAxis.setDrawGridLines(false)
            axisLeft.setDrawGridLines(false)
            axisRight.isEnabled = false
            legend.isEnabled = false
            
            data = LineData(LineDataSet(entries, "Breathing").apply {
                color = Color.GREEN
                setDrawCircles(false)
                setDrawValues(false)
                mode = LineDataSet.Mode.CUBIC_BEZIER
                lineWidth = 2f
            })
        }
    }

    private fun startVideoStreamThread() {
        thread {
            try {
                val videoServerIP = "192.168.50.175" // Replace with your video server's IP
                val videoServerPort = 9999
                val videoSocket = Socket(videoServerIP, videoServerPort)
                val videoInputStream: InputStream = videoSocket.getInputStream()

                while (true) {
                    // Read frame size
                    val sizeBuffer = ByteArray(4)
                    videoInputStream.read(sizeBuffer)
                    val size = sizeBuffer.fold(0) { acc, byte -> (acc shl 8) + (byte.toInt() and 0xFF) }

                    // Read frame data
                    val frameBuffer = ByteArray(size)
                    var bytesRead = 0
                    while (bytesRead < size) {
                        bytesRead += videoInputStream.read(frameBuffer, bytesRead, size - bytesRead)
                    }

                    // Decode and display frame
                    val bitmap = BitmapFactory.decodeByteArray(frameBuffer, 0, size)
                    runOnUiThread {
                        videoView.setImageBitmap(bitmap)
                    }
                }
            } catch (e: Exception) {
                e.printStackTrace()
                runOnUiThread {
                    breathingRateTextView.text = "Video Error: ${e.localizedMessage}"
                }
            }
        }
    }

    private fun startBreathingDataThread() {
        thread {
            try {
                val dataServerIP = "192.168.50.175" // Replace with your data server's IP
                val dataServerPort = 32345
                val dataSocket = Socket(dataServerIP, dataServerPort)
                val dataInput = DataInputStream(dataSocket.getInputStream())

                while (true) {
                    val value = dataInput.readFloat()
                    updateChart(value)
                }
            } catch (e: Exception) {
                e.printStackTrace()
                runOnUiThread {
                    breathingRateTextView.text = "Data Error: ${e.localizedMessage}"
                }
            }
        }
    }

    private fun updateChart(value: Float) {
        runOnUiThread {
            if (entries.size > maxDataPoints) {
                entries.removeAt(0)
            }
            entries.add(Entry(entries.size.toFloat(), value))
            
            breathingChart.data.notifyDataChanged()
            breathingChart.notifyDataSetChanged()
            breathingChart.setVisibleXRange(0f, maxDataPoints.toFloat())
            breathingChart.moveViewToX(entries.size.toFloat())
        }
    }
}
