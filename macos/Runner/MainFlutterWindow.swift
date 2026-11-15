import Cocoa
import FlutterMacOS
import PDFKit
import Vision
import ImageIO

/// Hosts the Flutter view in the main AppKit window.
class MainFlutterWindow: NSWindow {
  /// Installs the Flutter view controller and registers desktop plugins.
  override func awakeFromNib() {
    let flutterViewController = FlutterViewController()
    let windowFrame = self.frame
    self.contentViewController = flutterViewController
    self.setFrame(windowFrame, display: true)

    RegisterGeneratedPlugins(registry: flutterViewController)

    let attachments = FlutterMethodChannel(
      name: "almg/attachments", binaryMessenger: flutterViewController.engine.binaryMessenger
    )
    attachments.setMethodCallHandler { call, result in
      guard call.method == "extract",
            let arguments = call.arguments as? [String: Any],
            let bytes = arguments["bytes"] as? FlutterStandardTypedData,
            let format = arguments["format"] as? String else {
        result(FlutterMethodNotImplemented)
        return
      }
      DispatchQueue.global(qos: .userInitiated).async {
        let text = Self.attachmentText(bytes.data, format: format)
        DispatchQueue.main.async { result(text) }
      }
    }

    super.awakeFromNib()
  }

  /// Extracts page text from PDFs or recognizes text in a downscaled image.
  private static func attachmentText(_ bytes: Data, format: String) -> String {
    if format == "pdf" {
      guard let document = PDFDocument(data: bytes) else { return "" }
      var text = ""
      for index in 0..<min(document.pageCount, 40) {
        if let page = document.page(at: index)?.string, !page.isEmpty {
          text += "Page \(index + 1)\n" + String(page.prefix(12_000)) + "\n"
        }
        if text.count >= 12_000 { break }
      }
      return String(text.prefix(12_000))
    }
    guard let source = CGImageSourceCreateWithData(bytes as CFData, nil),
          let image = CGImageSourceCreateThumbnailAtIndex(source, 0, [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceThumbnailMaxPixelSize: 2048,
            kCGImageSourceCreateThumbnailWithTransform: true
          ] as CFDictionary) else { return "" }
    let request = VNRecognizeTextRequest()
    do {
      try VNImageRequestHandler(cgImage: image).perform([request])
    } catch {
      return ""
    }
    let text = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
      .joined(separator: "\n")
    return String(text.prefix(12_000))
  }
}
