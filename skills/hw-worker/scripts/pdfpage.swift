// Copyright 2026 Teklabs Digital (hw-skills)
// SPDX-License-Identifier: Apache-2.0
// Render PDF pages to PNG. macOS only (PDFKit and AppKit).
//   swift pdfpage.swift in.pdf <page (1-based)> out.png [scale]   one page
//   swift pdfpage.swift in.pdf all <prefix> [scale]               every page, as <prefix>_p<page>.png;
//                                                                 a file already there is left as it is
import AppKit
import Foundation
import PDFKit

func usage() -> Never {
    FileHandle.standardError.write("usage: pdfpage in.pdf page out.png [scale] | pdfpage in.pdf all prefix [scale]\n"
        .data(using: .utf8)!)
    exit(1)
}

func render(_ page: PDFPage, _ scale: CGFloat, _ out: String) throws {
    let box = page.bounds(for: .mediaBox)
    let w = Int(box.width * scale), h = Int(box.height * scale)
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: w, pixelsHigh: h, bitsPerSample: 8,
                               samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                               colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    let ctx = NSGraphicsContext(bitmapImageRep: rep)!
    NSGraphicsContext.current = ctx
    ctx.cgContext.setFillColor(NSColor.white.cgColor)
    ctx.cgContext.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.cgContext.scaleBy(x: scale, y: scale)
    page.draw(with: .mediaBox, to: ctx.cgContext)
    ctx.flushGraphics()
    try rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: out))
    print("wrote", out, w, h)
}

let args = CommandLine.arguments
guard args.count >= 4, let doc = PDFDocument(url: URL(fileURLWithPath: args[1])) else { usage() }
// Default scale 3 (216 dots per inch): small figure and drawing text stays legible. A pass that needs
// more renders one page again at a larger scale into its own file, never over a shared render.
let scale = args.count > 4 ? CGFloat(Double(args[4]) ?? 3) : 3
if args[2] == "all" {
    var kept = 0
    for i in 0..<doc.pageCount {
        let out = "\(args[3])_p\(i + 1).png"
        if FileManager.default.fileExists(atPath: out) {
            kept += 1
            continue
        }
        try render(doc.page(at: i)!, scale, out)
    }
    print("pages \(doc.pageCount); already there and left as they were: \(kept)")
} else {
    guard let num = Int(args[2]), num >= 1, let page = doc.page(at: num - 1) else { usage() }
    try render(page, scale, args[3])
}
