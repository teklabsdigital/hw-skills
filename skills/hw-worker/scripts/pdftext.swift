// Copyright 2026 Teklabs Digital (hw-skills)
// SPDX-License-Identifier: Apache-2.0
// Text extract of a PDF, one block per page: swift pdftext.swift in.pdf out.txt
// macOS only (PDFKit).
// It prints the pages with no text layer (scanned pages, drawings saved as images) and the pages with
// very little text (often an image with only a footer as text): read those from the page renders.
import Foundation
import PDFKit

let args = CommandLine.arguments
guard args.count == 3, let doc = PDFDocument(url: URL(fileURLWithPath: args[1])) else {
    FileHandle.standardError.write("usage: pdftext in.pdf out.txt\n".data(using: .utf8)!)
    exit(1)
}
var out = ""
var empty: [Int] = []
var little: [Int] = []
for i in 0..<doc.pageCount {
    let text = doc.page(at: i)?.string ?? ""
    let chars = text.filter { !$0.isWhitespace }.count
    var mark = ""
    if chars == 0 {
        empty.append(i + 1)
        mark = " (no text layer: read the page render)"
    } else if chars < 40 {
        little.append(i + 1)
        mark = " (little text: read the page render)"
    }
    out += "\n===== page \(i + 1)\(mark) =====\n"
    out += text
}
try out.write(toFile: args[2], atomically: true, encoding: .utf8)
print("pages:", doc.pageCount, "chars:", out.count)
func list(_ pages: [Int]) -> String { pages.isEmpty ? "none" : pages.map { String($0) }.joined(separator: ", ") }
print("pages with no text layer (read them from the renders):", list(empty))
print("pages with under 40 characters of text (check them on the renders):", list(little))
