import streamlit as st
from htbuilder import HtmlElement, div, ul, li, br, hr, a, p, img, styles, classes, fonts
from htbuilder.units import percent, px
from htbuilder.funcs import rgba, rgb


def image(src_as_string, **style):
    return img(src=src_as_string, style=styles(**style))


def link(link, text, **style):
    return a(_href=link, _target="_blank", style=styles(**style))(text)


# MainMenu {visibility: hidden;}
def layout(*args):

    hide_stuff = """
    <style>
      #MainMenu {visibility: hidden;}
      footer {visibility: hidden;}
      .stApp { bottom: 100px; }
      .stMain {
            flex: 1;
            align-items: flex-start;
            overflow-x: hidden;
        }
        iframe{
            # width: 100%;
            width:76vw;
        }
        .stMainBlockContainer  .stVerticalBlock {
            width: 76vw;
        }
        .stAppHeader {
            box-shadow: 0 2px 8px #f0f1f2;
        }
    </style>
    """

    style_div = styles(
        position="fixed",
        left=0,
        bottom=0,
        margin=px(0, 0, 0, 0),
        width=percent(100),
        color="black",
        text_align="center",
        height="auto",
        opacity=1
    )

    style_hr = styles(
        #display="block",
        margin=px(0, 0, "auto", "auto"),
        #border_style="inset",
        border_width=px(3)
    )

    body = p()
    foot = div(
        style=style_div
    )(
        hr(
          style=style_hr
        ),
        body
    )

    for arg in args:
        if isinstance(arg, str):
            body(arg)

        elif isinstance(arg, HtmlElement):
            body(arg)

    st.markdown(hide_stuff, unsafe_allow_html=True)
    st.markdown(str(foot), unsafe_allow_html=True)


def footer():
    myargs = [
        "Made in &nbsp; ",
        image('https://avatars3.githubusercontent.com/u/45109972?s=400&v=4',
              width=px(25), height=px(25)),
        "	&nbsp; by &nbsp;",
        link("https://www.tredence.com/services/industry-x-iot-solution", "@Tredence"),
    ]
    layout(*myargs)


if __name__ == "__main__":
    footer()