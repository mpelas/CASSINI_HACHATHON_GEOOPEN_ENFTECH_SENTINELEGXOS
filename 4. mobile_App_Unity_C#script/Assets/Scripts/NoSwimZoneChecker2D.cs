using UnityEngine;
using UnityEngine.UI;
using UnityEngine.Networking;
using System.Collections;
using System.Text;
using TMPro;
using System.IO;

/// <summary>
/// A C# script for a Unity 2D app that checks for no-swimming zones based on GPS coordinates
/// and displays the location on a Google Maps static image.
/// FIXED VERSION: Proper map rendering, auto-scrolling logs, and reliable button handling
/// </summary>
public class NoSwimZoneChecker2D : MonoBehaviour
{
    [Header("UI Components")]
    public TextMeshProUGUI statusText;
    public Image backgroundOverlay;
    public RawImage mapImage;  // Changed to RawImage for better texture handling
    public AudioSource alarmSound;
    
    [Header("Log Components")]
    public TextMeshProUGUI logText;
    public ScrollRect logScrollRect;  // Add reference to ScrollRect
    public Button clearLogButton;
    public Button saveLogButton;

    [Header("Settings")]
    public float checkInterval = 10f;
    public int mapZoomLevel = 15;
    public int mapImageSize = 640;  // Increased for better quality

    // The URL for the Google Cloud Function
    private const string ApiUrl = "https://mpelas-wastewater-203451079784.europe-west1.run.app";

    // *** IMPORTANT: REPLACE WITH YOUR KEY ***
    private const string GoogleMapsApiKey = "AIzaSyAm6NN3vZ7UAe86j0Y4tXO0OLuULcaGcBQ"; 
    
    private bool isFlashing = false;
    private string currentLogFilePath = "";

    // ============================================
    // JSON DATA STRUCTURES - Full API Response
    // ============================================
    
    [System.Serializable]
    public class ApiResponse
    {
        public bool in_no_swim_zone;
        public string compliance_status;
        public Coordinates coordinates;
        public ZoneDetails zone_details;
    }

    [System.Serializable]
    public class Coordinates
    {
        public float latitude;
        public float longitude;
    }

    [System.Serializable]
    public class ZoneDetails
    {
        public string code;
        public string name;
        public string nameEn;
        public string municipal;
        public string municipalEn;
        public string administrativeRegion;
        public string administrativeRegionEn;
        public string receiverName;
        public string receiverNameEn;
        public string receiverCode;
        public bool receiverSensitive;
        public int receiverWaterType;
        public int capacity;
        public int year;
        public bool compliance;
        public string priority;
        public string priorityEn;
        public bool priorityId;
        public string riverBasin;
        public string riverBasinEn;
        public string riverBasinDistrict;
        public string riverBasinDistrictEn;
        public float latitude;
        public float longitude;
        public string wasteTreatmentMethod;
        public string sludgeTreatmentMethod;
        public bool reuse;
    }

    void Start()
    {
        // Validate all required components
        if (statusText == null || backgroundOverlay == null || alarmSound == null || 
            logText == null || mapImage == null)
        {
            Debug.LogError("CRITICAL: UI, Audio, or Map components are not assigned in the Inspector!");
            if (statusText != null) statusText.text = "Initialization Error: Missing UI/Audio components.";
            return;
        }

        // Initialize UI
        backgroundOverlay.color = new Color(0, 0.7f, 0, 0.5f);
        statusText.text = "Initializing GPS...";
        statusText.color = Color.white;
        logText.text = "";

        // Setup buttons with listeners
        SetupButtons();

        // Create timestamped log file name
        string timestamp = System.DateTime.Now.ToString("yyyyMMdd_HHmmss");
        currentLogFilePath = Path.Combine(Application.persistentDataPath, $"NoSwimLog_{timestamp}.txt");
        
        AppendLogEntry("=== NO-SWIM ZONE CHECKER ===");
        AppendLogEntry($"Application Initialized (2D Mode)");
        AppendLogEntry($"Log file: {currentLogFilePath}");
        AppendLogEntry($"Persistent data path: {Application.persistentDataPath}");

        StartCoroutine(StartGPSAndCheck());
    }

    /// <summary>
    /// Setup button listeners with error checking
    /// </summary>
    private void SetupButtons()
    {
        if (clearLogButton != null)
        {
            // Remove any existing listeners first (safety measure)
            clearLogButton.onClick.RemoveAllListeners();
            clearLogButton.onClick.AddListener(ClearLog);
            Debug.Log("Clear Log button listener added successfully");
        }
        else
        {
            Debug.LogWarning("Clear Log Button is not assigned in Inspector!");
        }

        if (saveLogButton != null)
        {
            saveLogButton.onClick.RemoveAllListeners();
            saveLogButton.onClick.AddListener(SaveAndShareLog);
            Debug.Log("Save/Share Log button listener added successfully");
        }
        else
        {
            Debug.LogWarning("Save Log Button is not assigned in Inspector!");
        }
    }

    private IEnumerator StartGPSAndCheck()
    {
        if (!Input.location.isEnabledByUser)
        {
            statusText.text = "Location services are not enabled.";
            statusText.color = Color.red;
            AppendLogEntry("ERROR: Location services disabled by user.");
            yield break;
        }

        AppendLogEntry("Requesting location service start...");
        Input.location.Start(10f, 10f); 

        int maxWait = 20;
        while (Input.location.status == LocationServiceStatus.Initializing && maxWait > 0)
        {
            AppendLogEntry($"Waiting for GPS initialization ({maxWait}s remaining)...");
            yield return new WaitForSeconds(1);
            maxWait--;
        }

        if (maxWait < 1 || Input.location.status == LocationServiceStatus.Failed)
        {
            statusText.text = "Failed to start location service. Check device settings.";
            statusText.color = Color.red;
            AppendLogEntry("ERROR: Failed to start location service/Timed out.");
            yield break;
        }
        else
        {
            AppendLogEntry("Location services started successfully.");
            StartCoroutine(PeriodicCheck());
        }
    }

    private IEnumerator PeriodicCheck()
    {
        while (true)
        {
            yield return StartCoroutine(CheckNoSwimmingZone());
            yield return new WaitForSeconds(checkInterval);
        }
    }

    private IEnumerator CheckNoSwimmingZone()
    {
        yield return null; 

        float latitude = Input.location.lastData.latitude;
        float longitude = Input.location.lastData.longitude;
        float accuracy = Input.location.lastData.horizontalAccuracy;

        string locationMessage = $"GPS: Lat {latitude:F6}, Lon {longitude:F6}, Acc {accuracy:F1}m";
        AppendLogEntry("========================================");
        AppendLogEntry(locationMessage);

        statusText.text = $"{locationMessage}\nChecking compliance...";
        statusText.color = Color.white;

        yield return StartCoroutine(UpdateGoogleMaps(latitude, longitude));

        string requestUrl = $"{ApiUrl}?latitude={latitude}&longitude={longitude}";
        AppendLogEntry($"API REQUEST: {requestUrl}");

        using (UnityWebRequest www = UnityWebRequest.Get(requestUrl))
        {
            yield return www.SendWebRequest();

            if (www.result == UnityWebRequest.Result.ConnectionError || www.result == UnityWebRequest.Result.ProtocolError)
            {
                statusText.text = $"API Error ({www.responseCode}): {www.error}";
                statusText.color = Color.red;
                AppendLogEntry($"ERROR: API Request Failed. Code: {www.responseCode}, Reason: {www.error}");
                
                if (alarmSound.isPlaying) alarmSound.Stop();
                StopCoroutine("FlashBackground");
                isFlashing = false;
                backgroundOverlay.color = Color.red; 
            }
            else
            {
                string jsonResponse = www.downloadHandler.text;
                AppendLogEntry($"RAW API RESPONSE:");
                AppendLogEntry(jsonResponse);

                try
                {
                    ApiResponse response = JsonUtility.FromJson<ApiResponse>(jsonResponse);
                    
                    // Log all parsed data
                    AppendLogEntry("--- PARSED DATA ---");
                    AppendLogEntry($"In No-Swim Zone: {response.in_no_swim_zone}");
                    AppendLogEntry($"Compliance Status: {response.compliance_status}");
                    
                    if (response.coordinates != null)
                    {
                        AppendLogEntry($"Confirmed Coordinates: {response.coordinates.latitude:F6}, {response.coordinates.longitude:F6}");
                    }

                    // Display detailed zone information if in no-swim zone
                    if (response.zone_details != null && response.in_no_swim_zone)
                    {
                        AppendLogEntry("--- ZONE DETAILS ---");
                        AppendLogEntry($"Facility: {response.zone_details.nameEn} ({response.zone_details.name})");
                        AppendLogEntry($"Code: {response.zone_details.code}");
                        AppendLogEntry($"Municipality: {response.zone_details.municipalEn}");
                        AppendLogEntry($"Region: {response.zone_details.administrativeRegionEn}");
                        AppendLogEntry($"Receiver: {response.zone_details.receiverNameEn}");
                        AppendLogEntry($"Receiver Code: {response.zone_details.receiverCode}");
                        AppendLogEntry($"Capacity: {response.zone_details.capacity:N0} m³/day");
                        AppendLogEntry($"Year Established: {response.zone_details.year}");
                        AppendLogEntry($"Facility Compliance: {response.zone_details.compliance}");
                        AppendLogEntry($"Priority: {response.zone_details.priorityEn}");
                        AppendLogEntry($"River Basin: {response.zone_details.riverBasinEn}");
                        AppendLogEntry($"District: {response.zone_details.riverBasinDistrictEn}");
                        AppendLogEntry($"Treatment Method: {response.zone_details.wasteTreatmentMethod}");
                        AppendLogEntry($"Sensitive Receiver: {response.zone_details.receiverSensitive}");
                    }

                    if (response.in_no_swim_zone)
                    {
                        // NO SWIM ZONE - DANGER
                        string alertText = $"⚠️ DANGER! NO SWIMMING ZONE ⚠️\n" +
                                         $"Facility: {response.zone_details?.nameEn ?? "Unknown"}\n" +
                                         $"Status: {response.compliance_status}";
                        
                        statusText.text = alertText;
                        statusText.color = Color.yellow;
                        AppendLogEntry($"🚨 ALERT: ENTERING NO-SWIM ZONE!");
                        AppendLogEntry($"Compliance: {response.compliance_status}");
                        AppendLogEntry("⚠️ ALARM ACTIVATED ⚠️");

                        if (!isFlashing) StartCoroutine("FlashBackground");
                        if (!alarmSound.isPlaying)
                        {
                            alarmSound.loop = true;
                            alarmSound.Play();
                        }
                    }
                    else
                    {
                        // SAFE ZONE - ALL CLEAR
                        statusText.text = $"✓ ALL CLEAR - SAFE TO SWIM\nStatus: {response.compliance_status}";
                        statusText.color = Color.green;
                        AppendLogEntry($"✓ SAFE ZONE - Compliance: {response.compliance_status}");

                        if (alarmSound.isPlaying) alarmSound.Stop();
                        if (isFlashing)
                        {
                            StopCoroutine("FlashBackground");
                            isFlashing = false;
                        }
                        backgroundOverlay.color = new Color(0, 1, 0, 0.7f);
                    }
                }
                catch (System.Exception e)
                {
                    statusText.text = "Error parsing API response.";
                    statusText.color = Color.red;
                    AppendLogEntry($"❌ JSON PARSING ERROR: {e.Message}");
                    AppendLogEntry($"Stack Trace: {e.StackTrace}");
                }
            }
        }
    }

    /// <summary>
    /// Updated to use RawImage for better quality and proper aspect ratio
    /// </summary>
    private IEnumerator UpdateGoogleMaps(float latitude, float longitude)
    {
        string mapsUrl = $"https://maps.googleapis.com/maps/api/staticmap?" +
                        $"center={latitude},{longitude}" +
                        $"&zoom={mapZoomLevel}" +
                        $"&size={mapImageSize}x{mapImageSize}" +
                        $"&scale=2" +  // Higher quality for retina displays
                        $"&maptype=roadmap" +
                        $"&markers=color:red%7C{latitude},{longitude}" +
                        $"&key={GoogleMapsApiKey}";
        
        using (UnityWebRequest mapRequest = UnityWebRequestTexture.GetTexture(mapsUrl))
        {
            yield return mapRequest.SendWebRequest();

            if (mapRequest.result == UnityWebRequest.Result.Success)
            {
                Texture2D mapTexture = DownloadHandlerTexture.GetContent(mapRequest);
                
                // Apply texture to RawImage for pixel-perfect rendering
                mapImage.texture = mapTexture;
                mapImage.color = Color.white;
                
                AppendLogEntry("Google Maps updated successfully");
            }
            else
            {
                AppendLogEntry($"Google Maps error: {mapRequest.error}");
                mapImage.color = Color.gray;
            }
        }
    }

    // ============================================
    // LOGGING AND FILE MANAGEMENT
    // ============================================

    /// <summary>
    /// Append log entry with auto-scroll to bottom
    /// </summary>
    private void AppendLogEntry(string message)
    {
        string timestamp = System.DateTime.Now.ToString("HH:mm:ss.fff");
        string logEntry = $"[{timestamp}] {message}\n";

        // Update UI
        logText.text += logEntry;
        Debug.Log(logEntry);

        // Auto-scroll to bottom
        if (logScrollRect != null)
        {
            Canvas.ForceUpdateCanvases();
            logScrollRect.verticalNormalizedPosition = 0f;
        }

        // Save to file immediately
        try
        {
            File.AppendAllText(currentLogFilePath, logEntry);
        }
        catch (System.Exception e)
        {
            Debug.LogError($"Failed to write to log file: {e.Message}");
        }

        // Keep UI log from becoming too long
        if (logText.text.Length > 8000)
        {
            logText.text = logText.text.Substring(logText.text.Length - 4000);
            logText.text = "--- Log Truncated (full log in file) ---\n" + logText.text;
        }
    }

    public void ClearLog()
    {
        Debug.Log("ClearLog() called");
        logText.text = "--- Log Cleared (UI Only) ---\n";
        AppendLogEntry("User cleared UI log (file log continues)");
    }

    /// <summary>
    /// Saves the log file and opens the native share dialog (Android/iOS)
    /// </summary>
    public void SaveAndShareLog()
    {
        Debug.Log("SaveAndShareLog() called");
        AppendLogEntry("User requested to save/share log");
        
        if (!File.Exists(currentLogFilePath))
        {
            AppendLogEntry("ERROR: Log file does not exist!");
            return;
        }

        // Display file location
        AppendLogEntry($"Log saved to: {currentLogFilePath}");
        AppendLogEntry($"File size: {new FileInfo(currentLogFilePath).Length} bytes");
        
        // For Android/iOS - use native sharing
        #if UNITY_ANDROID || UNITY_IOS
        StartCoroutine(ShareLogFile());
        #else
        // For other platforms, just log the location
        AppendLogEntry("DESKTOP MODE: File saved. Manual sharing required.");
        AppendLogEntry("To share: Navigate to the path above and attach to email.");
        
        // Open the folder in file explorer (Windows/Mac)
        Application.OpenURL("file://" + Application.persistentDataPath);
        #endif
    }

    /// <summary>
    /// Native sharing for Android/iOS using Unity's built-in capabilities
    /// </summary>
    private IEnumerator ShareLogFile()
    {
        yield return new WaitForEndOfFrame();

        #if UNITY_ANDROID
        ShareFileAndroid();
        #elif UNITY_IOS
        ShareFileIOS();
        #endif
    }

    #if UNITY_ANDROID
    private void ShareFileAndroid()
    {
        try
        {
            // Create Android intent to share file
            using (AndroidJavaClass intentClass = new AndroidJavaClass("android.content.Intent"))
            using (AndroidJavaObject intentObject = new AndroidJavaObject("android.content.Intent"))
            {
                intentObject.Call<AndroidJavaObject>("setAction", intentClass.GetStatic<string>("ACTION_SEND"));
                
                using (AndroidJavaClass uriClass = new AndroidJavaClass("android.net.Uri"))
                using (AndroidJavaObject uriObject = uriClass.CallStatic<AndroidJavaObject>("parse", "file://" + currentLogFilePath))
                {
                    intentObject.Call<AndroidJavaObject>("putExtra", intentClass.GetStatic<string>("EXTRA_STREAM"), uriObject);
                    intentObject.Call<AndroidJavaObject>("setType", "text/plain");
                    intentObject.Call<AndroidJavaObject>("putExtra", intentClass.GetStatic<string>("EXTRA_SUBJECT"), 
                        "NoSwimZone Log - " + System.DateTime.Now.ToString("yyyy-MM-dd HH:mm"));
                    intentObject.Call<AndroidJavaObject>("putExtra", intentClass.GetStatic<string>("EXTRA_TEXT"), 
                        "No-Swim Zone Checker compliance log attached.");

                    using (AndroidJavaClass unity = new AndroidJavaClass("com.unity3d.player.UnityPlayer"))
                    using (AndroidJavaObject currentActivity = unity.GetStatic<AndroidJavaObject>("currentActivity"))
                    {
                        AndroidJavaObject chooser = intentClass.CallStatic<AndroidJavaObject>("createChooser", intentObject, "Share Log File");
                        currentActivity.Call("startActivity", chooser);
                    }
                }
            }
            
            AppendLogEntry("Android share dialog opened");
        }
        catch (System.Exception e)
        {
            AppendLogEntry($"Android share error: {e.Message}");
            AppendLogEntry($"File location: {currentLogFilePath}");
        }
    }
    #endif

    #if UNITY_IOS
    private void ShareFileIOS()
    {
        // For iOS, you'll need to use native plugin or manually copy file
        AppendLogEntry("iOS: Log saved to app documents folder");
        AppendLogEntry($"Path: {currentLogFilePath}");
        AppendLogEntry("Use iTunes File Sharing or Files app to access the log.");
        
        // Alternative: Copy to clipboard
        GUIUtility.systemCopyBuffer = File.ReadAllText(currentLogFilePath);
        AppendLogEntry("Log content copied to clipboard!");
    }
    #endif

    private IEnumerator FlashBackground()
    {
        isFlashing = true;
        while (true)
        {
            backgroundOverlay.color = new Color(1, 0, 0, 0.4f);
            yield return new WaitForSeconds(0.5f);
            backgroundOverlay.color = new Color(0.5f, 0, 0, 0.2f);
            yield return new WaitForSeconds(0.5f);
        }
    }
}