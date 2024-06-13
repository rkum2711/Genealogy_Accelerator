from neo4j import GraphDatabase
from pyvis.network import Network
import dotenv
import os
import streamlit as st
from layout import footer
import streamlit.components.v1 as components
import json
import re

uri = st.secrets["NEO4J_URI"]
auth = (st.secrets["NEO4J_USERNAME"], st.secrets["NEO4J_PASSWORD"])
driver = GraphDatabase.driver(uri, auth=auth)

with open('./config.json', 'r') as file:
    config = json.load(file)


options_list = [
    "Manufacturing Knowledge Graph",
    "Batch Genealogy",
    "Assets Traceability",
    # "Show Selective Assets",
    # "Ask More Questions-(GEN AI)"
  ]
asset_questions = [
    "View Lineage of all Asset", 
    # "List down assets that has AMC and insurance < 2 year",
    # "List down assets that has high downtime Percentage (MTBF)",
    # "List down assets that has high Efficiency(OEE)",
    # "List down assets that has low Efficiency(OEE)",
    # "Show asset maintenance summary", 
    # "show asset spare part inventory consumption summary"
    ]
batch_questions = ["View Lineage of all Batches"]
html_file_path = config["html_file_path"]
network_html_file_path = config["network_html_file_path"]
chatgpt_icon = config["chatgpt_icon"]
legend_mapping = config["legend_mapping"]

def get_neo4j_data(query,session):
    data = session.run(query)
    return data

def get_id_list(node):
    with driver.session() as session:
        results = session.run(f"MATCH (n:{node}) RETURN n.id")
        id_list = sorted([row["n.id"] for row in results])
        return id_list

@st.cache_data
def get_asset_data():
    with st.spinner("Connecting GraphDB"):
        batch_ids = get_id_list("batch") 
        asset_ids = get_id_list("asset")
        facility_ids = get_id_list("facility") 
        site_ids = get_id_list("site") 
        region_ids = get_id_list("region") 
        po_ids = get_id_list("po")
        product_ids = get_id_list("product")  
        supplier_ids = get_id_list("supplier")  
        material_ids = get_id_list("material")
        wo_ids = get_id_list("wo")  
        return batch_ids, asset_ids, facility_ids, site_ids, region_ids,po_ids,product_ids,supplier_ids,material_ids,wo_ids

def generate_nodes_edges(data):
    net = Network(
        notebook=False,
        cdn_resources="remote",
        bgcolor="white",
        font_color="black",
        height="750px",
        width="100%",
        select_menu=True,
        # filter_menu=False
    )
    # net.show_buttons(filter_=True)
    # Adjust physics settings
    net.barnes_hut(gravity=-50000, central_gravity=0.3, spring_length=75, spring_strength=0.05, damping=0.09)
    # net.repulsion()
    added_nodes = set()
    node_properties = {}
    for record in data:
        for key, value in record.items():
            if value is not None and "id" in value.keys() and value["id"] not in added_nodes:
                node_id = value.get('id')
                node_label = list(value.labels)[0].upper() if value.labels else "UNKNOWN"
                node_color = legend_mapping.get(node_label, "#000000")
                node_prop_html = "\n".join(f"{k} : {v}" for k, v in value._properties.items())
                net.add_node(node_id, label=value.get('Name'), title=node_prop_html, color = node_color)
                added_nodes.add(node_id)
                node_properties[node_id] = value._properties

        for key, value in record.items():
            if value is not None and hasattr(value, 'start_node'):
                if value.start_node["id"] in added_nodes and value.end_node["id"] in added_nodes:
                    net.add_edge(value.start_node["id"], value.end_node["id"], title=value.type)
    return net, node_properties

def save_graph_file(graph,html_file_path):
    top_position=150
    # Add legend to the HTML file
    legend_html = f"""
    <style>
        #legend {{
            position: absolute;
            top: {top_position}px; /* Adjusted top position */
            right: 10px;
            background: rgba(255, 255, 255, 0.8);
            border: 1px solid black;
            padding: 10px;
            display: none; /* Initially hidden */
            z-index: 1000;
        }}
        #legend h5 {{
            margin: 0;
            padding: 0;
            text-align: center;
        }}
        #legend ul {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}
        #legend li {{
            margin: 5px 0;
            display: flex;
            align-items: center;
        }}
        #legend span {{
            width: 15px;
            height: 15px;
            display: inline-block;
            margin-right: 10px;
            border: 1px solid #000;
        }}
        #legend-toggle {{
            position: absolute;
            top: {top_position - 40}px; /* Adjusted top position */
            right: 10px;
            padding: 5px 10px;
            background: #28a745; /* Green color */
            color: white;
            border: none;
            cursor: pointer;
            z-index: 1000;
        }}
        #legend-toggle:hover {{
            background: #218838; /* Darker green on hover */
        }}
    </style>
    <button id="legend-toggle">Toggle Legend</button>
    <div id="legend">
        <h5>Node Legend</h5>
        <ul>
    """
    for node_type, color in legend_mapping.items():
        legend_html += f'<li><span style="background: {color};"></span> {node_type}</li>'
    legend_html += """
        </ul>
    </div>
    <script>
        document.getElementById('legend-toggle').addEventListener('click', function() {
            var legend = document.getElementById('legend');
            if (legend.style.display === 'none' || legend.style.display === '') {
                legend.style.display = 'block';
            } else {
                legend.style.display = 'none';
            }
        });
    </script>
    """
    graph.save_graph(html_file_path)
    with open(html_file_path, 'r', encoding='utf-8') as html_file:
        source_code = html_file.read()
    updated_html = source_code.replace("</body>", legend_html + "</body>")
    with open(html_file_path, 'w', encoding='utf-8') as html_file:
        html_file.write(updated_html)
    components.html(updated_html, height=1200, width=1200)
    
def app():
    footer()
    st.title("Batch genealogy - Graph DB")
    # st.image(gdm_image, caption='', width=1000)
    batch_ids, asset_ids, facility_ids, site_ids, region_ids,po_ids,product_ids,supplier_ids,material_ids,wo_ids = get_asset_data()
    facility, site, region = st.columns(3)
    with facility:
        st.info(f"Total Facilities : {len(facility_ids)}")
    with site:
        st.info(f"Total Sites : {len(site_ids)}")
    with region:
        st.info(f"Total Region : {len(region_ids)}")
    col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
    option = st.sidebar.radio('Select Options', options_list)
    if option == options_list[0]:
        with col1:
            st.success(f"Total Batches: {len(batch_ids)}")
        with col2:
            st.info(f"Total PO : {len(po_ids)}")
        with col3:
            st.info(f"Total Products : {len(product_ids)}")
        with col4:
            st.info(f"Total material : {len(material_ids)}")
        with col5:
            st.info(f"Total Suppliers : {len(supplier_ids)}")
        with col6:
            st.success(f"Total Assets: {len(asset_ids)}")
        with col7:
            st.info(f"Total Work Orders : {len(wo_ids)}")
        st.subheader(option)
        tab1, tab2= st.tabs(["Selected Batch Network", "Whole Network",])
        with tab2:
            st.header("Whole Network")
            with st.spinner("Executing query..."):
                try:
                    with st.spinner("Data Loading ...."):
                        query = """
                        MATCH (b:batch)<-[pb:pBatch]-(po:po)
                        MATCH (po)<-[ppo:productPo]-(p:product)
                        MATCH (p)<-[rp:recipeProduct]-(r:recipe)
                        MATCH (r)<-[mr:materialRecipe]-(m:material)
                        MATCH (m)<-[pmmm:pmMaterial]-(pm:plant_material)
                        MATCH (pm)<-[fpm:facilityPm]-(f:facility)
                        MATCH (f)-[fs:facilitySite]->(s:site)
                        MATCH (s)-[sr:siteRegion]->(re:region)
                        MATCH (b)<-[bwo:batchWo]->(wo:wo)
                        MATCH (wo)<-[awo:assetWo]->(a:asset)
                        MATCH (a)-[al:assetline]->(l:line)
                        MATCH (l)-[lf:lineFacility]->(af:facility)
                        MATCH (af)-[afs:facilitySite]->(as:site)
                        MATCH (as)-[asr:siteRegion]->(ar:region) 
                        RETURN *
                        """
                        # with driver.session() as session:
                        #     graphData = get_neo4j_data(query,session)
                        #     with st.spinner("Converting into Graph ..."):
                        #         graph, node_properties = generate_nodes_edges(graphData)
                        #         save_graph_file(graph, network_html_file_path)
                        with st.spinner("Converting into Graph ..."):
                            HtmlFile = open(network_html_file_path, 'r', encoding='utf-8')
                            network_source_code = HtmlFile.read() 
                            components.html(network_source_code,height=1200, width=1200)
                except Exception as e:
                    st.error(f"Error executing query: {e}")
                st.write("Query execution complete")
        with tab1:
            st.header("Selected Batch Network")
            selected_batch = st.selectbox("Select batch? ", batch_ids)
            if st.button("Search"):
                with st.spinner("Executing query..."):
                    try:
                        with st.spinner("Data Loading ...."):
                            query = f"""
                            MATCH (b:batch {{id: '{selected_batch}'}})<-[pb:pBatch]-(po:po)
                            MATCH (po)<-[ppo:productPo]-(p:product)
                            MATCH (p)<-[rp:recipeProduct]-(r:recipe)
                            MATCH (r)<-[mr:materialRecipe]-(m:material)
                            MATCH (m)<-[pmmm:pmMaterial]-(pm:plant_material)
                            MATCH (pm)<-[fpm:facilityPm]-(f:facility)
                            MATCH (f)-[fs:facilitySite]->(s:site)
                            MATCH (s)-[sr:siteRegion]->(re:region)
                            MATCH (b)<-[bwo:batchWo]->(wo:wo)
                            MATCH (wo)<-[awo:assetWo]->(a:asset)
                            MATCH (a)-[al:assetline]->(l:line)
                            MATCH (l)-[lf:lineFacility]->(af:facility)
                            MATCH (af)-[afs:facilitySite]->(as:site)
                            MATCH (as)-[asr:siteRegion]->(ar:region) 
                            RETURN *
                            """
                            with driver.session() as session:
                                graphData = get_neo4j_data(query,session)
                                with st.spinner("Converting into Graph ..."):
                                    graph, node_properties = generate_nodes_edges(graphData)
                                    save_graph_file(graph, html_file_path)
                    except Exception as e:
                        st.error(f"Error executing query: {e}")
                    st.write("Query execution complete")
    elif option == options_list[1]:
        with col1:
            st.success(f"Total Batches: {len(batch_ids)}")
        with col2:
            st.info(f"Total PO : {len(po_ids)}")
        with col3:
            st.info(f"Total Products : {len(product_ids)}")
        with col4:
            st.info(f"Total material : {len(material_ids)}")
        with col5:
            st.info(f"Total Suppliers : {len(supplier_ids)}")
        st.subheader(option)
        query_type = st.selectbox("Select Questions? ", asset_questions)
        if st.button("Search"):
            for q in asset_questions:
                if query_type == q:
                    st.subheader(query_type)
                    with st.spinner("Executing query..."):
                        try:
                            with st.spinner("Data Loading ...."):
                                if q == asset_questions[0]:
                                    query = """
                                    MATCH (a:asset)-[al:assetline]->(l:line)
                                    MATCH (l)-[lf:lineFacility]->(f:facility)
                                    MATCH (f)-[fs:facilitySite]->(s:site)
                                    MATCH (s)-[sr:siteRegion]->(r:region) 
                                    RETURN *
                                    """
                                with driver.session() as session:
                                    graphData = get_neo4j_data(query,session)
                                    with st.spinner("Converting into Graph ..."):
                                        graph, node_properties = generate_nodes_edges(graphData)
                                        save_graph_file(graph, html_file_path)
                        except Exception as e:
                            st.error(f"Error executing query: {e}")
                        st.write("Query execution complete")
    elif option == options_list[2]:
        with col1:
            st.success(f"Total Assets: {len(asset_ids)}")
        with col2:
            st.info(f"Total Work Orders : {len(wo_ids)}")
        st.subheader(option)
        query_type = st.selectbox("Select Questions? ", batch_questions)
        if st.button("Search"):
            for q in batch_questions:
                if query_type == q:
                    st.subheader(query_type)
                    with st.spinner("Executing query..."):
                        try:
                            with st.spinner("Data Loading ...."):
                                if q == batch_questions[0]:
                                    query = """
                                    MATCH (b:batch)<-[pb:pBatch]-(po:po)
                                    MATCH (po)<-[ppo:productPo]-(p:product)
                                    MATCH (p)<-[rp:recipeProduct]-(r:recipe)
                                    MATCH (r)<-[mr:materialRecipe]-(m:material)
                                    MATCH (m)<-[pmmm:pmMaterial]-(pm:plant_material)
                                    MATCH (pm)<-[fpm:facilityPm]-(f:facility)
                                    MATCH (f)-[fs:facilitySite]->(s:site)
                                    MATCH (s)-[sr:siteRegion]->(re:region)
                                    RETURN *
                                    """
                                with driver.session() as session:
                                    graphData = get_neo4j_data(query,session)
                                    with st.spinner("Converting into Graph ..."):
                                        graph, node_properties = generate_nodes_edges(graphData)
                                        save_graph_file(graph,html_file_path)
                        except Exception as e:
                            st.error(f"Error executing query: {e}")
                        st.write("Query execution complete")
if __name__ == "__main__":
    app()