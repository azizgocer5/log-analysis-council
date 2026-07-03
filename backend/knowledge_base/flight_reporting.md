# Flight Reporting

PX4 logs detailed aircraft state and sensor data, which can be used to analyze performance issues. This topic explains how you can download and analyse logs, and share them with the development team for review.

TIP

Keeping flight logs is a legal requirement in some jurisdictions.

## Downloading Logs from the Flight Controller

Logs can be downloaded using QGroundControl: Analyze View > Log Download.

TIP

Encrypted logs cannot be downloaded with QGroundControl, or uploaded to the public Flight Review service. The easiest way to download and extract encrypted logs is to use the Log Encryption Tools. You can also host a private Flight Review server that automatically decrypts logs on upload using your private key.

## Analyzing the Logs

Upload the log file to the online Flight Review tool. After upload you'll be emailed a link to the analysis page for the log.

Log Analysis using Flight Review explains how to interpret the plots, and can help you to verify/reject the causes of common problems: excessive vibration, poor PID tuning, saturated controllers, imbalanced vehicles, GPS noise, etc.

INFO

There are many other great tools for visualising and analysing PX4 Logs. For more information see: Flight Analysis.

TIP

If you have a constant high-rate MAVLink connection to the vehicle (not just a telemetry link) then you can use QGroundControl to automatically upload logs directly to Flight Review. For more information see Settings > MAVLink Settings > MAVLink 2 Logging (PX4 only).

## Sharing the Log Files for Review by PX4 Developers

The Flight Review log file link can be shared for discussion in the support forums or a Github issue.

## Log Configuration

The logging system is configured by default to collect sensible logs for use with Flight Review.

Logging may further be configured using the SD Logging parameters or with a file on the SD card. Details on configuration can be found in the logging configuration documentation.

## Key Links
- Flight Review
- Log Analysis using Flight Review
- Flight Log Analysis Edit on GitHubPagerPrevious pageMissionsNext pageFlight Log Analysis