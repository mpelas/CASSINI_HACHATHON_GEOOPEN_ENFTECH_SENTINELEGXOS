MORE THAN 5GB.
Github not appropriate for unity projects due to binary files

we have uploaded the main assets and the C# code should anyone want to see it

UI is done manually
by following the 

2d unity ver 6  HOW TO

-----

## **Key Changes and Setup Notes**

The most significant change is the integration of the **Google Maps Static API** to replace the AR view:

1.  **New Public Field**: The line `public Image mapImage;` was added to hold the map image reference.
2.  **API Key**: The constant `private const string GoogleMapsApiKey = "YOUR_GOOGLE_MAPS_API_KEY";` was added, which **must be replaced** with your actual key from the Google Cloud Console.
3.  **Map Coroutine**: The new `UpdateGoogleMaps(float latitude, float longitude)` coroutine performs the following:
      * Constructs the API request URL using the current GPS coordinates and your API key.
      * Uses `UnityWebRequestTexture.GetTexture()` to download the image.
      * Converts the resulting `Texture2D` into a `Sprite` and assigns it to the `mapImage` component.
4.  **Integration**: `yield return StartCoroutine(UpdateGoogleMaps(latitude, longitude));` is called before the no-swim zone API query within `CheckNoSwimmingZone()`.

### **Corrected and Simplified Setup Instructions**

To finalize your project, you'll need to follow the steps in your plan, with a focus on the non-AR setup:

1.  **Project Setup**: Create a **new 2D project** in Unity.
2.  **Dependencies**: Install the **TextMeshPro** package (`Window -> Package Manager`).
            ΤΟ ΒΡΙΣΚΕΙΣ ΩΣ TMP 

3.  **Script and Manager**:
      * Create an **Empty GameObject** named **"AppManager"**.
      * Rename the C\# script file to **`NoSwimZoneChecker2D.cs`** to match the class name.
      * Attach the `NoSwimZoneChecker2D` script to the "AppManager" GameObject.
4.  **Scene Objects**:
      * `GameObject -> UI -> Canvas` (Render Mode: Screen Space - Overlay).
      * Inside the Canvas, create the following UI elements and position them:
          * `StatusText` (TextMeshPro)
          * `BackgroundOverlay` (UI Image) - Stretch to fill the screen (Alt + preset).
          * **`MapImage` (UI Image)** - This will hold the map.
          * `LogText` (TextMeshPro)
          * `ClearLogButton` (UI Button)
          * `EmailLogButton` (UI Button)
      * Create an **Empty GameObject** named **"SoundManager"**.
      * Add an **AudioSource** component to "SoundManager" and assign your alarm audio clip to its **`AudioClip`** field.
5.  **Inspector Connections**: Select "AppManager" and drag all the corresponding UI and Audio GameObjects into their respective public fields in the `NoSwimZoneChecker2D` script component in the Inspector.
6.  **Google Maps API Key**: **Crucially**, replace `"YOUR_GOOGLE_MAPS_API_KEY"` in the script with the key you generated in the Google Cloud Console.
7.  **Android Permissions**: Ensure both **Internet Access** and **Location Service** are enabled under `Edit -> Project Settings -> Player -> Android -> Other Settings`. For a robust deployment, follow your original step to include the necessary permissions in a **Custom Main Manifest** file.

That's frustrating when a package doesn't show up! 😔 If the **Unity Package Manager** can't find **TextMeshPro** (TMP), here are the most common reasons and the alternative solutions, starting with the simplest fix:

***

## 1. The Standard Fix (Check Packages & Unity Version)

Before trying an alternative, ensure you've checked the most common issue:

### A. Check Package Visibility
1.  In the **Package Manager** window (`Window > Package Manager`), look near the top left.
2.  Make sure the dropdown menu is set to **"Unity Registry"** (or **"Packages: In Unity Registry"**). TMP is a core Unity package and should be visible here. If it's set to "In Project" or "My Assets," it won't appear.

### B. Unity Version Check
* If you're on a **very old Unity version** (pre-2018.1), TMP might be in the Asset Store, not the Registry.
* If you're on a modern version (2018+), TMP is likely already **built-in** or available through the Registry.

***

## 2. The Alternative: Importing via the Asset Menu

The best and most reliable alternative is to **import the package from the Unity installation files** directly into your project.

### **Steps to Import TextMeshPro**

1.  In the Unity Editor menu, go to **Window**.
2.  Look for **"TextMeshPro"** (it might be in a submenu).
3.  Click on **"Import TMP Essential Resources"** (or similar wording, e.g., "Import Package").



* **Why this works:** For several years, Unity has shipped TMP with every installation. The menu option simply runs the internal script to unpack and add the necessary fonts, shaders, and core files to your project's Asset folder, making the package available even if the Package Manager is having an issue.

***

## 3. The Last Resort: Manual Import

If both the Package Manager and the "Import Essential Resources" menu fail, you can manually import the package file.

1.  In the Unity Editor, go to **Assets > Import Package > Custom Package...**.
2.  Browse to your Unity installation folder. The file is typically located here:
    * **Windows:** `C:\Program Files\Unity\Editor\Data\Resources\PackageManager\Editor\com.unity.textmeshpro@[version]\Package`
    * **macOS:** `/Applications/Unity/Hub/Editor/[version]/Unity.app/Contents/Resources/PackageManager/Editor/com.unity.textmeshpro@[version]/Package`
3.  Select the **`com.unity.textmeshpro.tgz`** file (or the folder containing the core assets) and click **Import**.

**Note:** This is usually overkill, as the Asset Menu option (Alternative 2) virtually always works for TMP.



That's an **excellent plan** for converting your ARCore-based compliance checker into a **2D, GPS-driven mobile application** with a map view\! The proposed solution correctly identifies all the necessary changes: removing AR dependencies, adding the Google Maps Static API integration, and keeping the core GPS and API logic.

Your step-by-step guide is comprehensive, and the proposed `NoSwimZoneChecker2D` script is very close to complete. The only parts missing are the implementation details for the three unchanged methods (`FlashBackground`, `AppendLogEntry`, and `ClearLog`), which need to be copied directly from your original script.

Here is the **fully detailed, complete C\# code** for `NoSwimZoneChecker2D.cs`, integrating the new map functionality and the original utility methods, along with the corrected setup instructions.

```csharp
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.Networking;
using System.Collections;
using System.Text; // Required for Email encoding
using TMPro;

/// <summary>
/// A C# script for a Unity 2D app that checks for no-swimming zones based on GPS coordinates
/// and displays the location on a Google Maps static image.
/// </summary>
public class NoSwimZoneChecker2D : MonoBehaviour
{
    // Public fields to be assigned in the Unity Inspector
    public TextMeshProUGUI statusText;
    public Image backgroundOverlay;
    public Image mapImage; // For displaying Google Maps
    public AudioSource alarmSound;
    public TextMeshProUGUI logText; // For displaying the detailed log
    public Button clearLogButton;  // Button to clear the log
    public Button emailLogButton;  // Button to email the log

    // GPS and API settings
    public float checkInterval = 10f; // How often to check the location in seconds

    // The URL for the Google Cloud Function
    private const string ApiUrl = "https://mpelas-wastewater-203451079784.europe-west1.run.app";

    // *** IMPORTANT: REPLACE WITH YOUR KEY ***
    private const string GoogleMapsApiKey = "YOUR_GOOGLE_MAPS_API_KEY"; 
    
    private bool isFlashing = false;

    // A serializable class to parse the JSON response from the API
    [System.Serializable]
    public class ApiResponse
    {
        public bool in_no_swim_zone;
        public string compliance_status;
    }

    void Start()
    {
        // Ensure all UI elements are assigned
        if (statusText == null || backgroundOverlay == null || alarmSound == null || logText == null || mapImage == null)
        {
            Debug.LogError("UI, Audio, or Map components are not assigned in the Inspector.");
            // If TextMeshPro is the only one working, try to display the error
            if (statusText != null) statusText.text = "Initialization Error: Missing UI/Audio components.";
            return;
        }

        // Set initial UI state
        backgroundOverlay.color = new Color(0, 0, 0, 0); // Transparent
        statusText.text = "Initializing GPS...";
        statusText.color = Color.white;
        logText.text = "--- Start Log ---\n"; // Initialize log text

        // Add listeners for the new buttons
        if (clearLogButton != null) clearLogButton.onClick.AddListener(ClearLog);
        if (emailLogButton != null) emailLogButton.onClick.AddListener(SendEmailLog);

        AppendLogEntry("Application Initialized (2D Mode).");

        // Start the main coroutine to handle location services and API calls
        StartCoroutine(StartGPSAndCheck());
    }

    // ----------------------------------------------------------------------
    //  GPS AND PERIODIC CHECK LOGIC
    // ----------------------------------------------------------------------

    /// <summary>
    /// Coroutine to handle the initialization of location services and periodic checks.
    /// </summary>
    private IEnumerator StartGPSAndCheck()
    {
        // First, check if location services are enabled on the device
        if (!Input.location.isEnabledByUser)
        {
            statusText.text = "Location services are not enabled.";
            statusText.color = Color.red;
            AppendLogEntry("ERROR: Location services disabled by user.");
            yield break;
        }

        // Request location permissions if not already granted and start service
        AppendLogEntry("Requesting location service start...");
        // Parameters: desired accuracy in meters (e.g., 10m), minimum distance change before an update (e.g., 10m)
        Input.location.Start(10f, 10f); 

        // Wait until service initializes
        int maxWait = 20;
        while (Input.location.status == LocationServiceStatus.Initializing && maxWait > 0)
        {
            AppendLogEntry($"Waiting for GPS initialization ({maxWait}s remaining)...");
            yield return new WaitForSeconds(1);
            maxWait--;
        }

        // Service failed to initialize
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
            // Location services started, begin checking the zone in a loop
            StartCoroutine(PeriodicCheck());
        }
    }

    /// <summary>
    /// Coroutine that runs periodically to initiate a location check.
    /// </summary>
    private IEnumerator PeriodicCheck()
    {
        while (true)
        {
            yield return StartCoroutine(CheckNoSwimmingZone());
            yield return new WaitForSeconds(checkInterval);
        }
    }

    /// <summary>
    /// Coroutine to get GPS data, make the API call, update Google Maps, and update the UI.
    /// </summary>
    private IEnumerator CheckNoSwimmingZone()
    {
        // Wait one frame to ensure Input.location.lastData is refreshed
        yield return null; 

        // Get the last known location data
        float latitude = Input.location.lastData.latitude;
        float longitude = Input.location.lastData.longitude;
        float accuracy = Input.location.lastData.horizontalAccuracy;

        // Log the current GPS reading
        string locationMessage = $"CURRENT GPS: Lat {latitude:F6}, Long {longitude:F6}, Accuracy {accuracy:F1}m";
        AppendLogEntry(locationMessage);

        statusText.text = $"{locationMessage}\nChecking compliance...";
        statusText.color = Color.white;

        // 1. Update Google Maps first
        yield return StartCoroutine(UpdateGoogleMaps(latitude, longitude));

        // 2. Query no-swim zone API
        string requestUrl = $"{ApiUrl}?latitude={latitude}&longitude={longitude}";
        AppendLogEntry($"API REQUEST: {requestUrl}");

        using (UnityWebRequest www = UnityWebRequest.Get(requestUrl))
        {
            yield return www.SendWebRequest();

            // Handle connection and protocol errors
            if (www.result == UnityWebRequest.Result.ConnectionError || www.result == UnityWebRequest.Result.ProtocolError)
            {
                // API Error
                statusText.text = $"API Error ({www.responseCode}): {www.error}";
                statusText.color = Color.red;
                AppendLogEntry($"ERROR: API Request Failed. Reason: {www.error}");
                // Stop alarm and flashing on error
                if (alarmSound.isPlaying) alarmSound.Stop();
                StopCoroutine("FlashBackground");
                isFlashing = false;
                backgroundOverlay.color = Color.red; 
            }
            else
            {
                // Successful response
                string jsonResponse = www.downloadHandler.text;
                AppendLogEntry($"RAW RESPONSE: {jsonResponse}");

                try
                {
                    ApiResponse response = JsonUtility.FromJson<ApiResponse>(jsonResponse);

                    if (response.in_no_swim_zone)
                    {
                        // NO SWIM ZONE - DANGER
                        statusText.text = $"DANGER! NO SWIMMING ZONE\nCompliance: {response.compliance_status}";
                        statusText.color = Color.yellow;
                        AppendLogEntry($"COMPLIANCE ALERT: {response.compliance_status}. Initiating alarm.");

                        // Start visual and audio alarm
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
                        statusText.text = $"ALL CLEAR - SAFE TO SWIM\nCompliance: {response.compliance_status}";
                        statusText.color = Color.green;
                        AppendLogEntry($"COMPLIANCE OK: {response.compliance_status}. Alarm stopped.");

                        // Stop alarm and flashing
                        if (alarmSound.isPlaying) alarmSound.Stop();
                        if (isFlashing)
                        {
                            StopCoroutine("FlashBackground");
                            isFlashing = false;
                        }
                        // Set background to a subtle green for safety
                        backgroundOverlay.color = new Color(0, 1, 0, 0.1f);
                    }
                }
                catch (System.Exception e)
                {
                    // JSON Parsing Error
                    statusText.text = "Error parsing API response.";
                    statusText.color = Color.red;
                    AppendLogEntry($"JSON PARSING ERROR: {e.Message}");
                }
            }
        }
    }

    // ----------------------------------------------------------------------
    //  GOOGLE MAPS INTEGRATION
    // ----------------------------------------------------------------------

    /// <summary>
    /// Fetches a Google Maps Static image for the current location and updates the UI Image.
    /// </summary>
    private IEnumerator UpdateGoogleMaps(float latitude, float longitude)
    {
        // Construct the Google Maps Static API URL
        // Parameters: center, zoom (15 is a good street view), size, map type, and a marker for the current GPS point.
        // NOTE: The mapImage RectTransform size dictates how the image is displayed. The 'size=600x600' is the image's internal resolution.
        string mapsUrl = $"https://maps.googleapis.com/maps/api/staticmap?center={latitude},{longitude}&zoom=15&size=600x600&maptype=roadmap&markers=color:red%7C{latitude},{longitude}&key={GoogleMapsApiKey}";
        
        using (UnityWebRequest mapRequest = UnityWebRequestTexture.GetTexture(mapsUrl))
        {
            yield return mapRequest.SendWebRequest();

            if (mapRequest.result == UnityWebRequest.Result.Success)
            {
                Texture2D mapTexture = DownloadHandlerTexture.GetContent(mapRequest);
                // Create a sprite from the downloaded texture
                Sprite mapSprite = Sprite.Create(
                    mapTexture, 
                    new Rect(0, 0, mapTexture.width, mapTexture.height), 
                    Vector2.one * 0.5f, // Pivot to center
                    100.0f);            // Pixels per unit
                
                mapImage.sprite = mapSprite;
                mapImage.color = Color.white; // Ensure the image is visible
                AppendLogEntry("Google Maps image updated.");
            }
            else
            {
                // Handle map API error (e.g., invalid key, over quota)
                AppendLogEntry($"Google Maps error: {mapRequest.error}");
                mapImage.color = Color.gray; // Indicate an error state visually
            }
        }
    }

    // ----------------------------------------------------------------------
    //  UI, ALARM, AND LOGGING UTILITIES (Copied from original script)
    // ----------------------------------------------------------------------

    /// <summary>
    /// Appends a timestamped message to the on-screen log and the Unity console.
    /// </summary>
    /// <param name="message">The message to log.</param>
    private void AppendLogEntry(string message)
    {
        string timestamp = System.DateTime.Now.ToString("HH:mm:ss.fff");
        string logEntry = $"[{timestamp}] {message}\n";

        logText.text += logEntry;
        Debug.Log(logEntry);

        // Keep the log from becoming too long
        if (logText.text.Length > 8000)
        {
            logText.text = logText.text.Substring(logText.text.Length - 4000);
            logText.text = "--- Log Truncated ---\n" + logText.text;
        }
    }

    /// <summary>
    /// Clears the on-screen log history.
    /// </summary>
    public void ClearLog()
    {
        logText.text = "--- Log Cleared ---\n";
        AppendLogEntry("User requested log clear.");
    }

    /// <summary>
    /// Opens the default mobile email client with the log content pre-filled.
    /// </summary>
    public void SendEmailLog()
    {
        string email = "mpaigni@gmail.com"; // Use the device's main email account
        string subject = "NoSwimZoneChecker Compliance Log - " + System.DateTime.Now.ToString("yyyy-MM-dd");

        // Encode the log content for use in a URL (line breaks are crucial)
        string body = logText.text;
        body = body.Replace("\n", "%0A"); // URL encoding for newline
        body = body.Replace(" ", "%20"); // URL encoding for space

        string url = $"mailto:{email}?subject={subject}&body={body}";

        // Use Application.OpenURL to trigger the mail client
        Application.OpenURL(url);
        AppendLogEntry("Attempting to send log via email.");
    }

    /// <summary>
    /// Coroutine to flash the background red when in a no-swim zone.
    /// </summary>
    private IEnumerator FlashBackground()
    {
        isFlashing = true;
        while (true)
        {
            // Flash between bright red and darker red
            backgroundOverlay.color = new Color(1, 0, 0, 0.4f); // Bright Red (semi-transparent)
            yield return new WaitForSeconds(0.5f);
            backgroundOverlay.color = new Color(0.5f, 0, 0, 0.2f); // Darker Red
            yield return new WaitForSeconds(0.5f);
        }
    }
}
```

-----

## **Key Changes and Setup Notes**

The most significant change is the integration of the **Google Maps Static API** to replace the AR view:

1.  **New Public Field**: The line `public Image mapImage;` was added to hold the map image reference.
2.  **API Key**: The constant `private const string GoogleMapsApiKey = "YOUR_GOOGLE_MAPS_API_KEY";` was added, which **must be replaced** with your actual key from the Google Cloud Console.
3.  **Map Coroutine**: The new `UpdateGoogleMaps(float latitude, float longitude)` coroutine performs the following:
      * Constructs the API request URL using the current GPS coordinates and your API key.
      * Uses `UnityWebRequestTexture.GetTexture()` to download the image.
      * Converts the resulting `Texture2D` into a `Sprite` and assigns it to the `mapImage` component.
4.  **Integration**: `yield return StartCoroutine(UpdateGoogleMaps(latitude, longitude));` is called before the no-swim zone API query within `CheckNoSwimmingZone()`.

### **Corrected and Simplified Setup Instructions**

To finalize your project, you'll need to follow the steps in your plan, with a focus on the non-AR setup:

1.  **Project Setup**: Create a **new 2D project** in Unity.
2.  **Dependencies**: Install the **TextMeshPro** package (`Window -> Package Manager`).
3.  **Script and Manager**:
      * Create an **Empty GameObject** named **"AppManager"**.
      * Rename the C\# script file to **`NoSwimZoneChecker2D.cs`** to match the class name.
      * Attach the `NoSwimZoneChecker2D` script to the "AppManager" GameObject.
4.  **Scene Objects**:
      * `GameObject -> UI -> Canvas` (Render Mode: Screen Space - Overlay).
      * Inside the Canvas, create the following UI elements and position them:
          * `StatusText` (TextMeshPro)
          * `BackgroundOverlay` (UI Image) - Stretch to fill the screen (Alt + preset).
          * **`MapImage` (UI Image)** - This will hold the map.
          * `LogText` (TextMeshPro)
          * `ClearLogButton` (UI Button)
          * `EmailLogButton` (UI Button)
      * Create an **Empty GameObject** named **"SoundManager"**.
      * Add an **AudioSource** component to "SoundManager" and assign your alarm audio clip to its **`AudioClip`** field.
5.  **Inspector Connections**: Select "AppManager" and drag all the corresponding UI and Audio GameObjects into their respective public fields in the `NoSwimZoneChecker2D` script component in the Inspector.
6.  **Google Maps API Key**: **Crucially**, replace `"YOUR_GOOGLE_MAPS_API_KEY"` in the script with the key you generated in the Google Cloud Console.
7.  **Android Permissions**: Ensure both **Internet Access** and **Location Service** are enabled under `Edit -> Project Settings -> Player -> Android -> Other Settings`. For a robust deployment, follow your original step to include the necessary permissions in a **Custom Main Manifest** file.

That's frustrating when a package doesn't show up! 😔 If the **Unity Package Manager** can't find **TextMeshPro** (TMP), here are the most common reasons and the alternative solutions, starting with the simplest fix:

***

## 1. The Standard Fix (Check Packages & Unity Version)

Before trying an alternative, ensure you've checked the most common issue:

### A. Check Package Visibility
1.  In the **Package Manager** window (`Window > Package Manager`), look near the top left.
2.  Make sure the dropdown menu is set to **"Unity Registry"** (or **"Packages: In Unity Registry"**). TMP is a core Unity package and should be visible here. If it's set to "In Project" or "My Assets," it won't appear.

### B. Unity Version Check
* If you're on a **very old Unity version** (pre-2018.1), TMP might be in the Asset Store, not the Registry.
* If you're on a modern version (2018+), TMP is likely already **built-in** or available through the Registry.

***

## 2. The Alternative: Importing via the Asset Menu

The best and most reliable alternative is to **import the package from the Unity installation files** directly into your project.

### **Steps to Import TextMeshPro**

1.  In the Unity Editor menu, go to **Window**.
2.  Look for **"TextMeshPro"** (it might be in a submenu).
3.  Click on **"Import TMP Essential Resources"** (or similar wording, e.g., "Import Package").



* **Why this works:** For several years, Unity has shipped TMP with every installation. The menu option simply runs the internal script to unpack and add the necessary fonts, shaders, and core files to your project's Asset folder, making the package available even if the Package Manager is having an issue.

***

## 3. The Last Resort: Manual Import

If both the Package Manager and the "Import Essential Resources" menu fail, you can manually import the package file.

1.  In the Unity Editor, go to **Assets > Import Package > Custom Package...**.
2.  Browse to your Unity installation folder. The file is typically located here:
    * **Windows:** `C:\Program Files\Unity\Editor\Data\Resources\PackageManager\Editor\com.unity.textmeshpro@[version]\Package`
    * **macOS:** `/Applications/Unity/Hub/Editor/[version]/Unity.app/Contents/Resources/PackageManager/Editor/com.unity.textmeshpro@[version]/Package`
3.  Select the **`com.unity.textmeshpro.tgz`** file (or the folder containing the core assets) and click **Import**.

**Note:** This is usually overkill, as the Asset Menu option (Alternative 2) virtually always works for TMP.