use super::*;
use std::path::{Component, Path};
pub fn checked_output(workspace: &str, output: &str) -> Result<PathBuf> {
    let raw = PathBuf::from(workspace);
    ensure!(
        raw.is_absolute() && raw.is_dir(),
        "Workspace must be an existing absolute directory"
    );
    let root = raw.canonicalize()?;
    let p = PathBuf::from(output);
    let p = if p.is_absolute() { p } else { raw.join(p) };
    ensure!(
        p.starts_with(&raw),
        "Preview output must be inside the workspace"
    );
    let mut normalized = PathBuf::new();
    for c in p.components() {
        match c {
            Component::ParentDir => {
                ensure!(normalized.pop(), "Invalid output path");
            }
            Component::CurDir => {}
            _ => normalized.push(c),
        }
    }
    ensure!(
        normalized.starts_with(&raw),
        "Preview output escapes workspace"
    );
    for part in normalized.ancestors() {
        if let Ok(m) = fs::symlink_metadata(part) {
            ensure!(
                !m.file_type().is_symlink(),
                "Preview paths cannot use symlinks or junctions"
            );
            #[cfg(windows)]
            {
                use std::os::windows::fs::MetadataExt;
                ensure!(
                    m.file_attributes() & 0x400 == 0,
                    "Preview paths cannot use symlinks or junctions"
                );
            }
        }
        if part == raw {
            break;
        }
    }
    fs::create_dir_all(&normalized)?;
    let resolved = normalized.canonicalize()?;
    ensure!(
        resolved.starts_with(root),
        "Preview output escapes workspace"
    );
    Ok(resolved)
}
fn pages(value: Option<&str>, total: u32) -> Result<Vec<u32>> {
    let Some(value) = value else {
        return Ok((1..=total.min(3)).collect());
    };
    let mut out = std::collections::BTreeSet::new();
    for part in value.split(',') {
        ensure!(
            regex::Regex::new(r"^[1-9]\d*(?:-[1-9]\d*)?$")
                .unwrap()
                .is_match(part),
            "Pages must look like 1,3-5"
        );
        let numbers: Vec<u32> = part
            .split('-')
            .map(str::parse)
            .collect::<std::result::Result<_, _>>()?;
        let start = numbers[0];
        let end = *numbers.last().unwrap();
        ensure!(
            start <= end && end <= total && end - start < 20,
            "Invalid page range, or more than 20 pages requested"
        );
        out.extend(start..=end);
    }
    ensure!(out.len() <= 20, "Preview at most 20 pages per call");
    Ok(out.into_iter().collect())
}
fn display(p: &Path) -> String {
    let p = p.to_string_lossy();
    if let Some(p) = p.strip_prefix(r"\\?\UNC\") {
        format!(r"\\{p}")
    } else {
        p.strip_prefix(r"\\?\").unwrap_or(&p).into()
    }
}
pub fn run(api: &Api, a: &Args) -> Result<Value> {
    let out = checked_output(a.required("workspace-root")?, a.required("output-dir")?)?;
    if a.group == "docs" {
        let url = format!(
            "https://www.googleapis.com/drive/v3/files/{}/export",
            enc(a.id()?)
        );
        let payload = api
            .client
            .get(url)
            .bearer_auth(&api.token)
            .query(&[("mimeType", "application/pdf")])
            .send()?
            .error_for_status()?
            .bytes()?;
        return render_pdf(
            &payload,
            &out,
            a.opts.get("pages").map(String::as_str),
            a.number("dpi", 144)? as u32,
        );
    }
    let mut seen = HashSet::new();
    let ids: Vec<_> = a
        .multi
        .get("slide-id")
        .context("Missing --slide-id")?
        .iter()
        .filter(|id| seen.insert(*id))
        .collect();
    ensure!(ids.len() <= 10, "Preview at most 10 slides per call");
    let base = format!(
        "https://slides.googleapis.com/v1/presentations/{}",
        enc(a.id()?)
    );
    let deck = api.get(&base, vec![("fields", "slides(objectId)".into())])?;
    ensure!(
        ids.iter()
            .all(|id| items(&deck["slides"]).iter().any(|s| s["objectId"] == **id)),
        "Requested slide ID is not in this presentation"
    );
    let folder = tempfile::Builder::new()
        .prefix("slides-preview-")
        .tempdir_in(out)?
        .keep();
    let client = Client::builder()
        .https_only(true)
        .timeout(std::time::Duration::from_secs(30))
        .build()?;
    let mut images = vec![];
    for (n, id) in ids.into_iter().enumerate() {
        let meta = api.get(
            &format!("{base}/pages/{}/thumbnail", enc(id)),
            vec![
                ("thumbnailProperties.mimeType", "PNG".into()),
                ("thumbnailProperties.thumbnailSize", "LARGE".into()),
            ],
        )?;
        let url = s(&meta["contentUrl"]);
        ensure!(url.starts_with("https://"), "Thumbnail URL must use HTTPS");
        let response = client.get(url).send()?.error_for_status()?;
        let mut payload = vec![];
        response
            .take(20 * 1024 * 1024 + 1)
            .read_to_end(&mut payload)?;
        ensure!(
            payload.len() <= 20 * 1024 * 1024 && payload.starts_with(b"\x89PNG\r\n\x1a\n"),
            "Thumbnail did not return a bounded PNG image"
        );
        let path = folder.join(format!("slide-{:03}.png", n + 1));
        fs::write(&path, payload)?;
        images.push(json!({"slide_id":id,"path":display(&path),"width":meta["width"],"height":meta["height"]}));
    }
    Ok(json!({"images":images,"visual_check":"not performed"}))
}
#[cfg(windows)]
pub fn render_pdf(
    payload: &[u8],
    output: &Path,
    selection: Option<&str>,
    dpi: u32,
) -> Result<Value> {
    use windows::{
        Data::Pdf::{PdfDocument, PdfPageRenderOptions},
        Graphics::Imaging::{BitmapDecoder, BitmapEncoder},
        Storage::Streams::{DataReader, DataWriter, InMemoryRandomAccessStream},
        Win32::System::WinRT::{RO_INIT_MULTITHREADED, RoInitialize, RoUninitialize},
        core::Interface,
    };
    ensure!((72..=200).contains(&dpi), "DPI must be between 72 and 200");
    ensure!(payload.starts_with(b"%PDF-"), "Export did not return a PDF");
    unsafe { RoInitialize(RO_INIT_MULTITHREADED)? };
    struct Com;
    impl Drop for Com {
        fn drop(&mut self) {
            unsafe { RoUninitialize() }
        }
    }
    let _com = Com;
    let input = InMemoryRandomAccessStream::new()?;
    let writer = DataWriter::CreateDataWriter(&input.GetOutputStreamAt(0)?)?;
    writer.WriteBytes(payload)?;
    let store: windows_future::IAsyncOperation<u32> = writer.StoreAsync()?.cast()?;
    store.join()?;
    input.Seek(0)?;
    let pdf = PdfDocument::LoadFromStreamAsync(&input)?.join()?;
    let total = pdf.PageCount()?;
    let selected = pages(selection, total)?;
    for n in &selected {
        let page = pdf.GetPage(n - 1)?;
        let size = page.Size()?;
        ensure!(
            size.Width as f64 * size.Height as f64 * (dpi as f64 / 96.).powi(2) <= 20_000_000.,
            "Page dimensions exceed the preview pixel limit"
        );
    }
    let folder = tempfile::Builder::new()
        .prefix("docs-preview-")
        .tempdir_in(output)?
        .keep();
    let pdf_path = folder.join("document.pdf");
    fs::write(&pdf_path, payload)?;
    let mut images = vec![];
    for n in &selected {
        let page = pdf.GetPage(n - 1)?;
        let size = page.Size()?;
        let options = PdfPageRenderOptions::new()?;
        let width = (size.Width as f64 * dpi as f64 / 96.).ceil() as u32;
        let height = (size.Height as f64 * dpi as f64 / 96.).ceil() as u32;
        options.SetDestinationWidth(width)?;
        options.SetDestinationHeight(height)?;
        options.SetBackgroundColor(windows::UI::Color {
            A: 255,
            R: 255,
            G: 255,
            B: 255,
        })?;
        let stream = InMemoryRandomAccessStream::new()?;
        page.RenderWithOptionsToStreamAsync(&stream, &options)?
            .join()?;
        // WinRT can incorporate desktop display scaling. Normalize exported
        // pixels so --dpi is independent of the user's monitor settings.
        let decoder = BitmapDecoder::CreateAsync(&stream)?.join()?;
        let stream = if decoder.PixelWidth()? != width || decoder.PixelHeight()? != height {
            let resized = InMemoryRandomAccessStream::new()?;
            let encoder = BitmapEncoder::CreateForTranscodingAsync(&resized, &decoder)?.join()?;
            encoder.BitmapTransform()?.SetScaledWidth(width)?;
            encoder.BitmapTransform()?.SetScaledHeight(height)?;
            encoder.FlushAsync()?.join()?;
            resized
        } else {
            stream
        };
        let len = stream.Size()?;
        ensure!(
            len <= 100 * 1024 * 1024,
            "Rendered preview exceeds size limit"
        );
        let reader = DataReader::CreateDataReader(&stream.GetInputStreamAt(0)?)?;
        let load: windows_future::IAsyncOperation<u32> = reader.LoadAsync(len as u32)?.cast()?;
        load.join()?;
        let mut bytes = vec![0; len as usize];
        reader.ReadBytes(&mut bytes)?;
        let path = folder.join(format!("page-{n:03}.png"));
        fs::write(&path, bytes)?;
        images.push(display(&path));
        page.Close()?;
    }
    Ok(
        json!({"pdf_path":display(&pdf_path),"images":images,"pages":selected,"total_pages":total,"visual_check":"not performed"}),
    )
}
#[cfg(not(windows))]
pub fn render_pdf(_: &[u8], _: &Path, _: Option<&str>, _: u32) -> Result<Value> {
    bail!(
        "This build uses the Windows native PDF renderer; build a renderer for this platform before distributing"
    )
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    #[cfg(windows)]
    fn native_pdf_renderer_produces_png() {
        // Minimal valid PDF with one blank page; entirely offline.
        let objects = [
            "<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 72 72] /Resources << >> >>",
        ];
        let mut pdf = String::from("%PDF-1.4\n");
        let mut offsets = vec![];
        for (i, object) in objects.iter().enumerate() {
            offsets.push(pdf.len());
            pdf.push_str(&format!("{} 0 obj\n{}\nendobj\n", i + 1, object));
        }
        let start = pdf.len();
        pdf.push_str("xref\n0 4\n0000000000 65535 f \n");
        for offset in offsets {
            pdf.push_str(&format!("{offset:010} 00000 n \n"));
        }
        pdf.push_str(&format!(
            "trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n"
        ));
        let dir = tempfile::tempdir().unwrap();
        let result = render_pdf(pdf.as_bytes(), dir.path(), None, 144).unwrap();
        assert_eq!(result["total_pages"], 1);
        let png = fs::read(result["images"][0].as_str().unwrap()).unwrap();
        assert!(png.starts_with(b"\x89PNG\r\n\x1a\n"));
        assert_eq!(u32::from_be_bytes(png[16..20].try_into().unwrap()), 144);
    }
    #[test]
    fn ranges_and_escape() {
        assert_eq!(pages(Some("1,3-4"), 5).unwrap(), vec![1, 3, 4]);
        assert!(pages(Some("1-21"), 30).is_err());
        let root = tempfile::tempdir().unwrap();
        assert!(checked_output(root.path().to_str().unwrap(), "../escape").is_err());
    }
}
