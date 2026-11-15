import Cocoa
import FlutterMacOS

/// Configures application termination and state restoration.
@main
class AppDelegate: FlutterAppDelegate {
  /// Quits ALMG when its last window closes.
  override func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
    return true
  }

  /// Enables secure AppKit state restoration.
  override func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool {
    return true
  }
}
