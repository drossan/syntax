import { memo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Elementos permitidos (allow-list, ADR-0020) — lo demás se "desenvuelve" a texto plano
 * (`unwrapDisallowed`), nunca desaparece en silencio. Sin `rehype-raw`: el Markdown fuente nunca se
 * interpreta como HTML — es la garantía anti-XSS central (`cross-cutting.md` §1, NFR-004). Las
 * casillas de lista-de-tareas de GFM (`- [ ] paso`) quedan fuera a propósito: sin estado que
 * persista, un checkbox no-interactivo no tiene sentido de producto aquí.
 */
const ALLOWED_ELEMENTS = [
  "p",
  "strong",
  "em",
  "del",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "ul",
  "ol",
  "li",
  "a",
  "img",
  "code",
  "pre",
  "blockquote",
  "table",
  "thead",
  "tbody",
  "tr",
  "th",
  "td",
  "hr",
  "br",
];

const HEADING_CLASS_NAME = "text-base font-semibold";

const markdownComponents: Components = {
  h1: (props) => <h1 className={HEADING_CLASS_NAME} {...props} />,
  h2: (props) => <h2 className={HEADING_CLASS_NAME} {...props} />,
  h3: (props) => <h3 className={HEADING_CLASS_NAME} {...props} />,
  h4: (props) => <h4 className={HEADING_CLASS_NAME} {...props} />,
  h5: (props) => <h5 className={HEADING_CLASS_NAME} {...props} />,
  h6: (props) => <h6 className={HEADING_CLASS_NAME} {...props} />,
  // Sin `urlTransform` propio: `react-markdown` ya sanea `href`/`src` vía `defaultUrlTransform`
  // (neutraliza `javascript:` sin config adicional — verificado, ADR-0020).
  a: ({ href, children, ...props }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
      {children}
    </a>
  ),
  // `referrerPolicy`/`loading` evitan que cargar una imagen externa filtre en qué ticket está el
  // usuario (vía `Referer`) al servidor de esa imagen. `next/image` no aplica aquí: exige conocer el
  // host en build-time (`remotePatterns`) o un import estático — estas URLs vienen de texto Markdown
  // de origen no confiable, arbitrarias en runtime.
  img: ({ src, alt, ...props }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} referrerPolicy="no-referrer" loading="lazy" {...props} />
  ),
  table: (props) => <table className="border-collapse" {...props} />,
  th: (props) => <th className="border px-2 py-1" {...props} />,
  td: (props) => <td className="border px-2 py-1" {...props} />,
  hr: (props) => <hr className="border-t" {...props} />,
};

/**
 * Renderiza texto Markdown de origen no confiable (draft IA, mensaje de ticket) de forma segura: un
 * allow-list explícito de elementos, sin interpretar HTML embebido (ADR-0020). `React.memo` —
 * mitigación preventiva ante el polling extensivo del hilo/notificaciones, sin evidencia de que haga
 * falta.
 *
 * @param children Texto Markdown a renderizar.
 */
function MarkdownTextComponent({ children }: { children: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      allowedElements={ALLOWED_ELEMENTS}
      unwrapDisallowed
      components={markdownComponents}
    >
      {children}
    </ReactMarkdown>
  );
}

export const MarkdownText = memo(MarkdownTextComponent);
