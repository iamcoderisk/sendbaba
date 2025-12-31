"""
SendBaba JSON Template Engine
Converts JSON template definitions to HTML for email rendering.
"""

import json
import re
from typing import Dict, List, Optional

# Default styles for elements
DEFAULT_STYLES = {
    "heading": {
        "h1": {"fontSize": "32px", "fontWeight": "700", "color": "#1f2937", "margin": "0", "lineHeight": "1.3"},
        "h2": {"fontSize": "24px", "fontWeight": "700", "color": "#1f2937", "margin": "0", "lineHeight": "1.3"},
        "h3": {"fontSize": "20px", "fontWeight": "600", "color": "#1f2937", "margin": "0", "lineHeight": "1.4"},
        "h4": {"fontSize": "18px", "fontWeight": "600", "color": "#374151", "margin": "0", "lineHeight": "1.4"},
    },
    "text": {"fontSize": "16px", "color": "#4b5563", "margin": "0", "lineHeight": "1.7"},
    "button": {
        "backgroundColor": "#F97316",
        "color": "#ffffff",
        "padding": "14px 32px",
        "borderRadius": "8px",
        "fontWeight": "600",
        "fontSize": "15px",
        "textDecoration": "none",
        "display": "inline-block"
    },
    "image": {"maxWidth": "100%", "height": "auto", "borderRadius": "8px"},
    "divider": {"borderTop": "2px solid #e2e8f0", "margin": "0"},
    "spacer": {"height": "32px"},
    "logo": {"maxHeight": "60px"},
    "social": {"iconSize": "36px", "gap": "12px"},
    "footer": {"fontSize": "13px", "color": "#64748b", "textAlign": "center"}
}


class TemplateRenderer:
    """Renders JSON template to HTML."""
    
    @staticmethod
    def render(template: Dict) -> str:
        """Render complete template to HTML."""
        if isinstance(template, str):
            template = json.loads(template)
            
        global_styles = template.get("globalStyles", {})
        sections = template.get("sections", [])
        
        html_parts = [
            '<!DOCTYPE html>',
            '<html lang="en">',
            '<head>',
            '<meta charset="UTF-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
            f'<title>{template.get("subject", "Email")}</title>',
            TemplateRenderer._render_head_styles(global_styles),
            '</head>',
            f'<body style="margin:0;padding:0;background-color:{global_styles.get("backgroundColor", "#f4f4f5")};">',
            TemplateRenderer._render_preheader(template.get("preheader", "")),
            '<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse;">',
            '<tr><td align="center" style="padding:24px;">',
            f'<table role="presentation" cellpadding="0" cellspacing="0" width="{global_styles.get("maxWidth", "650px").replace("px", "")}" style="border-collapse:collapse;max-width:{global_styles.get("maxWidth", "650px")};width:100%;background-color:{global_styles.get("contentBackgroundColor", "#ffffff")};border-radius:12px;overflow:hidden;box-shadow:0 4px 6px rgba(0,0,0,0.05);">',
        ]
        
        for section in sections:
            html_parts.append(TemplateRenderer._render_section(section, global_styles))
        
        html_parts.extend([
            '</table>',
            '</td></tr>',
            '</table>',
            '</body>',
            '</html>'
        ])
        
        return '\n'.join(html_parts)
    
    @staticmethod
    def render_body_only(template: Dict) -> str:
        """Render only the body content (for editor preview)."""
        if isinstance(template, str):
            template = json.loads(template)
            
        global_styles = template.get("globalStyles", {})
        sections = template.get("sections", [])
        
        html_parts = []
        for section in sections:
            html_parts.append(TemplateRenderer._render_section(section, global_styles, editable=True))
        
        return '\n'.join(html_parts)
    
    @staticmethod
    def _render_head_styles(global_styles: Dict) -> str:
        return f'''<style>
            body {{ font-family: {global_styles.get("fontFamily", "Arial, sans-serif")}; }}
            a {{ color: {global_styles.get("defaultLinkColor", "#F97316")}; }}
            @media only screen and (max-width: 600px) {{
                table[role="presentation"] {{ width: 100% !important; }}
                td {{ padding: 16px !important; }}
                img {{ max-width: 100% !important; height: auto !important; }}
            }}
        </style>'''
    
    @staticmethod
    def _render_preheader(text: str) -> str:
        if not text:
            return ''
        return f'<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">{text}</div>'
    
    @staticmethod
    def _render_section(section: Dict, global_styles: Dict, editable: bool = False) -> str:
        style = section.get("style", {})
        elements = section.get("elements", [])
        section_id = section.get("id", "")
        section_type = section.get("type", "content")
        
        style_str = TemplateRenderer._build_style_string(style)
        data_attrs = f'data-section-id="{section_id}" data-section-type="{section_type}"' if editable else ''
        
        html = f'<tr><td {data_attrs} style="{style_str}">'
        for element in elements:
            html += TemplateRenderer._render_element(element, global_styles, editable)
        html += '</td></tr>'
        return html
    
    @staticmethod
    def _render_element(element: Dict, global_styles: Dict, editable: bool = False) -> str:
        el_type = element.get("type", "text")
        el_id = element.get("id", "")
        style = element.get("style", {})
        
        data_attrs = f'data-element-id="{el_id}" data-element-type="{el_type}"' if editable else ''
        content_editable = 'contenteditable="true"' if editable else ''
        
        if el_type == "heading":
            level = element.get("level", "h1")
            text = element.get("text", "Heading")
            default_style = DEFAULT_STYLES["heading"].get(level, DEFAULT_STYLES["heading"]["h1"])
            merged_style = {**default_style, **style}
            style_str = TemplateRenderer._build_style_string(merged_style)
            return f'<{level} {data_attrs} {content_editable} style="{style_str}">{text}</{level}>'
        
        elif el_type == "text":
            text = element.get("text", "")
            merged_style = {**DEFAULT_STYLES["text"], **style}
            style_str = TemplateRenderer._build_style_string(merged_style)
            return f'<p {data_attrs} {content_editable} style="{style_str}">{text}</p>'
        
        elif el_type == "image":
            src = element.get("src", "https://via.placeholder.com/600x300")
            alt = element.get("alt", "Image")
            link = element.get("link", "")
            merged_style = {**DEFAULT_STYLES["image"], **style}
            style_str = TemplateRenderer._build_style_string(merged_style)
            img_html = f'<img {data_attrs} src="{src}" alt="{alt}" style="{style_str}">'
            if link:
                return f'<a href="{link}" target="_blank">{img_html}</a>'
            return img_html
        
        elif el_type == "button":
            text = element.get("text", "Click Here")
            link = element.get("link", "#")
            btn_style = {**DEFAULT_STYLES["button"], **style}
            if "backgroundColor" not in style:
                btn_style["backgroundColor"] = global_styles.get("defaultButtonColor", "#F97316")
            if "color" not in style:
                btn_style["color"] = global_styles.get("defaultButtonTextColor", "#ffffff")
            if "borderRadius" not in style:
                btn_style["borderRadius"] = global_styles.get("defaultButtonRadius", "8px")
            style_str = TemplateRenderer._build_style_string(btn_style)
            return f'<div style="text-align:{style.get("align", "center")};padding:8px 0;"><a {data_attrs} {content_editable} href="{link}" style="{style_str}">{text}</a></div>'
        
        elif el_type == "divider":
            merged_style = {**DEFAULT_STYLES["divider"], **style}
            style_str = TemplateRenderer._build_style_string(merged_style)
            return f'<hr {data_attrs} style="border:none;{style_str}">'
        
        elif el_type == "spacer":
            height = style.get("height", DEFAULT_STYLES["spacer"]["height"])
            return f'<div {data_attrs} style="height:{height};"></div>'
        
        elif el_type == "logo":
            src = element.get("src", "https://via.placeholder.com/200x60?text=LOGO")
            alt = element.get("alt", "Logo")
            link = element.get("link", "")
            merged_style = {**DEFAULT_STYLES["logo"], **style}
            style_str = TemplateRenderer._build_style_string(merged_style)
            img_html = f'<img {data_attrs} src="{src}" alt="{alt}" style="{style_str}">'
            if link:
                return f'<div style="text-align:{style.get("align", "center")};"><a href="{link}" target="_blank">{img_html}</a></div>'
            return f'<div style="text-align:{style.get("align", "center")};">{img_html}</div>'
        
        elif el_type == "social":
            networks = element.get("networks", [
                {"name": "facebook", "url": "#", "icon": "https://img.icons8.com/color/48/facebook-new.png"},
                {"name": "instagram", "url": "#", "icon": "https://img.icons8.com/color/48/instagram-new.png"},
                {"name": "twitter", "url": "#", "icon": "https://img.icons8.com/color/48/twitterx--v1.png"},
                {"name": "linkedin", "url": "#", "icon": "https://img.icons8.com/color/48/linkedin.png"}
            ])
            icon_size = style.get("iconSize", DEFAULT_STYLES["social"]["iconSize"])
            gap = style.get("gap", DEFAULT_STYLES["social"]["gap"])
            icons_html = ''.join([
                f'<a href="{n.get("url", "#")}" target="_blank" style="display:inline-block;margin:0 {gap};"><img src="{n.get("icon")}" width="{icon_size.replace("px", "")}" alt="{n.get("name")}" style="border-radius:4px;"></a>'
                for n in networks
            ])
            return f'<div {data_attrs} style="text-align:{style.get("align", "center")};padding:8px 0;">{icons_html}</div>'
        
        elif el_type == "columns":
            columns = element.get("columns", [])
            col_count = len(columns)
            col_width = 100 // col_count if col_count > 0 else 100
            cols_html = '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
            for col in columns:
                col_style = col.get("style", {})
                style_str = TemplateRenderer._build_style_string(col_style)
                cols_html += f'<td width="{col_width}%" valign="top" style="{style_str}">'
                for col_element in col.get("elements", []):
                    cols_html += TemplateRenderer._render_element(col_element, global_styles, editable)
                cols_html += '</td>'
            cols_html += '</tr></table>'
            return cols_html
        
        elif el_type == "list":
            items = element.get("items", [])
            list_type = element.get("listType", "ul")
            merged_style = {**DEFAULT_STYLES["text"], **style}
            style_str = TemplateRenderer._build_style_string(merged_style)
            items_html = ''.join([f'<li {content_editable}>{item}</li>' for item in items])
            return f'<{list_type} {data_attrs} style="{style_str};padding-left:20px;">{items_html}</{list_type}>'
        
        elif el_type == "html":
            return element.get("html", "")
        
        elif el_type == "footer":
            text = element.get("text", "© 2024 Company Name")
            address = element.get("address", "")
            unsubscribe = element.get("unsubscribeUrl", "{{unsubscribe_url}}")
            merged_style = {**DEFAULT_STYLES["footer"], **style}
            style_str = TemplateRenderer._build_style_string(merged_style)
            html = f'<div {data_attrs} style="{style_str}">'
            html += f'<p {content_editable} style="margin:0 0 8px;">{text}</p>'
            if address:
                html += f'<p {content_editable} style="margin:0 0 12px;font-size:12px;color:#94a3b8;">{address}</p>'
            html += f'<p style="margin:0;"><a href="{unsubscribe}" style="color:#64748b;text-decoration:underline;font-size:12px;">Unsubscribe</a></p>'
            html += '</div>'
            return html
        
        return f'<!-- Unknown element type: {el_type} -->'
    
    @staticmethod
    def _build_style_string(styles: Dict) -> str:
        css_map = {
            "fontSize": "font-size", "fontWeight": "font-weight", "fontFamily": "font-family",
            "lineHeight": "line-height", "textAlign": "text-align", "textDecoration": "text-decoration",
            "backgroundColor": "background-color", "borderRadius": "border-radius", "borderTop": "border-top",
            "maxWidth": "max-width", "maxHeight": "max-height", "letterSpacing": "letter-spacing"
        }
        parts = []
        for key, value in styles.items():
            css_key = css_map.get(key) or re.sub(r'([A-Z])', lambda m: '-' + m.group(1).lower(), key)
            parts.append(f"{css_key}:{value}")
        return ';'.join(parts)


def render_json_template(json_data) -> str:
    """Helper function to render JSON template to HTML."""
    return TemplateRenderer.render(json_data)


def render_json_template_body(json_data) -> str:
    """Helper function to render JSON template body only."""
    return TemplateRenderer.render_body_only(json_data)
