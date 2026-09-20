import Foundation
import Vision
import ImageIO

let url = URL(fileURLWithPath: CommandLine.arguments[1])
let source = CGImageSourceCreateWithURL(url as CFURL, nil)!
let image = CGImageSourceCreateImageAtIndex(source, 0, nil)!
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["en-US"]
try VNImageRequestHandler(cgImage: image).perform([request])
let rows: [[String: Any]] = (request.results ?? []).compactMap { observation in
    guard let text = observation.topCandidates(1).first?.string else { return nil }
    let box = observation.boundingBox
    return ["text": text, "x": box.midX, "y": 1 - box.midY]
}
let data = try JSONSerialization.data(withJSONObject: ["width": image.width, "height": image.height, "rows": rows], options: [.sortedKeys])
print(String(data: data, encoding: .utf8)!)
