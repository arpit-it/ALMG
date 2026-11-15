import Cocoa
import FlutterMacOS

/// Hosts the Flutter view in the main AppKit window.
class MainFlutterWindow: NSWindow {
  /// Installs the Flutter view controller and registers desktop plugins.
  override func awakeFromNib() {
    let flutterViewController = FlutterViewController()
    let windowFrame = self.frame
    self.contentViewController = flutterViewController
    self.setFrame(windowFrame, display: true)

    RegisterGeneratedPlugins(registry: flutterViewController)

    super.awakeFromNib()
  }
}
