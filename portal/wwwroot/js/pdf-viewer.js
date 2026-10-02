import * as pdfjs from '../vendor/pdfjs/build/pdf.min.mjs';
pdfjs.GlobalWorkerOptions.workerSrc = '/vendor/pdfjs/build/pdf.worker.min.mjs';

export function createViewer(elementId, url) {
    const root = document.getElementById(elementId);
    const get = name => root.querySelector(`[data-${name}]`);
    const canvas = root.querySelector('canvas');
    const wrap = root.querySelector('.pdf-canvas-wrap');
    let pdf = null, pageNumber = 1, busy = false, pending = false, disposed = false, renderTask = null;
    const listeners = [];
    const listen = (element, event, handler) => {
        element.addEventListener(event, handler);
        listeners.push(() => element.removeEventListener(event, handler));
    };
    const loading = pdfjs.getDocument({url, cMapUrl:'/vendor/pdfjs/cmaps/', cMapPacked:true,
        standardFontDataUrl:'/vendor/pdfjs/standard_fonts/', wasmUrl:'/vendor/pdfjs/wasm/', isEvalSupported:false});
    const update = () => {
        get('page').value = pageNumber;
        get('page').disabled = !pdf;
        get('page').max = pdf?.numPages ?? 1;
        get('pages').textContent = `de ${pdf?.numPages ?? '—'}`;
        get('previous').disabled = !pdf || pageNumber <= 1;
        get('next').disabled = !pdf || pageNumber >= pdf.numPages;
    };
    const render = async () => {
        if (!pdf || disposed) return;
        if (busy) { pending = true; return; }
        busy = true;
        try {
            do {
                pending = false;
                const number = pageNumber;
                get('pdf-status').textContent = 'Carregando página…';
                const page = await pdf.getPage(number);
                if (disposed) break;
                const base = page.getViewport({scale:1});
                const scale = get('zoom').value === 'fit' ? Math.max(.2,(wrap.clientWidth - 32) / base.width) : Number(get('zoom').value);
                const viewport = page.getViewport({scale});
                const density = Math.min(window.devicePixelRatio || 1,2);
                canvas.width = Math.floor(viewport.width * density);
                canvas.height = Math.floor(viewport.height * density);
                canvas.style.width = `${viewport.width}px`;
                canvas.style.height = `${viewport.height}px`;
                canvas.setAttribute('aria-label',`Página ${number} de ${pdf.numPages} do documento PDF`);
                renderTask = page.render({canvasContext:canvas.getContext('2d'),viewport,
                    transform:density === 1 ? null : [density,0,0,density,0,0]});
                await renderTask.promise;
                if (!disposed) {
                    get('pdf-status').textContent = `Página ${number} de ${pdf.numPages}`;
                    root.dataset.renderedPage = number;
                }
            } while (pending && !disposed);
        } catch (error) {
            if (!disposed) get('pdf-status').textContent = 'Não foi possível exibir a página. Use Abrir PDF para consultar o documento.';
        } finally { busy = false; }
    };
    const navigate = number => {
        if (!pdf) return;
        pageNumber = Math.max(1,Math.min(pdf.numPages,Number(number)||1));
        wrap.scrollTop = 0;
        update(); void render();
    };
    listen(get('previous'),'click',()=>navigate(pageNumber-1));
    listen(get('next'),'click',()=>navigate(pageNumber+1));
    listen(get('page'),'change',()=>navigate(get('page').value));
    listen(get('zoom'),'change',()=>void render());
    let width = wrap.clientWidth;
    const observer = new ResizeObserver(() => {
        if (width !== wrap.clientWidth) { width = wrap.clientWidth; if (get('zoom').value === 'fit') void render(); }
    });
    observer.observe(wrap);
    loading.promise.then(document => {
        if (disposed) { void document.destroy(); return; }
        pdf = document; update(); void render();
    }).catch(() => {
        if (!disposed) get('pdf-status').textContent = 'Não foi possível abrir o PDF. Verifique o arquivo ou use Abrir PDF.';
    });
    return {dispose() {
        disposed = true; observer.disconnect(); listeners.forEach(remove => remove());
        renderTask?.cancel(); void loading.destroy();
    }};
}
