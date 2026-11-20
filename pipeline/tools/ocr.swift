// 用 macOS Vision 识别图片里的文字，每张图输出一行 JSON：
//   {"image": 路径, "width": 宽, "height": 高, "lines": [{"text", "x", "y", "w", "h", "conf"}]}
// 坐标以图片左上角为原点、单位是像素（Vision 原生是左下角原点的归一化坐标）。
// 编译：swiftc -O tools/ocr.swift -o tools/ocr     用法：tools/ocr a.png b.png ...
import Foundation
import Vision
import AppKit

func recognize(_ path: String) -> [String: Any] {
    guard let image = NSImage(contentsOfFile: path),
          let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        return ["image": path, "error": "无法读取图片"]
    }
    let width = Double(cg.width), height = Double(cg.height)
    var lines: [[String: Any]] = []
    let request = VNRecognizeTextRequest { req, _ in
        for case let obs as VNRecognizedTextObservation in req.results ?? [] {
            guard let top = obs.topCandidates(1).first else { continue }
            let box = obs.boundingBox
            lines.append([
                "text": top.string,
                "x": box.minX * width,
                "y": (1 - box.maxY) * height,
                "w": box.width * width,
                "h": box.height * height,
                "conf": top.confidence,
            ])
        }
    }
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    request.usesLanguageCorrection = false  // 保留课本原样拼写，不让它「纠正」成别的词
    do {
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([request])
    } catch {
        return ["image": path, "error": "\(error)"]
    }
    return ["image": path, "width": width, "height": height, "lines": lines]
}

for path in CommandLine.arguments.dropFirst() {
    let result = recognize(path)
    let data = try! JSONSerialization.data(withJSONObject: result, options: [])
    print(String(data: data, encoding: .utf8)!)
}
