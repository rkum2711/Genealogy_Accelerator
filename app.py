from neo4j import GraphDatabase
from pyvis.network import Network
import streamlit as st
import json
import pandas as pd
import re
from layout import footer
import streamlit.components.v1 as components

# Configure Neo4j connection
uri = st.secrets["NEO4J_URI"]
auth = (st.secrets["NEO4J_USERNAME"], st.secrets["NEO4J_PASSWORD"])
driver = GraphDatabase.driver(uri, auth=auth)

# Load configuration
with open('./config.json', 'r') as file:
    config = json.load(file)
html_file_path = config["html_file_path"]
legend_mapping = config["legend_mapping"]
tredence_logo = config["tredence_logo"]
chatgpt_icon = config["chatgpt_icon"]

# Options
options_list = ["Manufacturing Knowledge Graph", "Batch Genealogy", "Assets Traceability"]
asset_questions = [
    "Asset Monitoring",
    "Provide a list of assets with both AMC and insurance coverage of less than 2 years?",
    "Identify the most utilized assets?"
]
batch_questions = [
    "Monitor the status and progress of all batches?",
    "Which materials are being consumed the most in the production process?",
    "Visualize how Process Orders are converted into batches?",
    "Which batches have a quality rating below 95%?",
    "How is the distribution of products across different warehouses managed?"
]

@st.cache_data
def get_id_list(node):
    """
    Fetch distinct IDs of a specific node type.
    """
    with driver.session() as session:
        query = f"MATCH (n:{node}) RETURN DISTINCT n.id"
        results = session.run(query)
        return sorted([row["n.id"] for row in results])

@st.cache_data
def get_asset_data():
    """
    Retrieve data for assets, batches, and related entities.
    """
    with st.spinner("Loading data from GraphDB..."):
        return {
            "batch_ids": get_id_list("Batch"),
            "asset_ids": get_id_list("Asset"),
            "facility_ids": get_id_list("Facility"),
            "site_ids": get_id_list("Site"),
            "region_ids": get_id_list("Region"),
            "po_ids": get_id_list("ProcessOrder"),
            "product_ids": get_id_list("Product"),
            "supplier_ids": get_id_list("Supplier"),
            "material_ids": get_id_list("Materials"),
            "wo_ids": get_id_list("WO")
        }

def get_graph_data(query,session):
    """  
    Execute a query and fetch graph data.
    """
    data = session.run(query)
    return data

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
    batch_connections = {}
    wo_connections = {}
    asset_connections = {}
    for record in data:
        for key, value in record.items():
            if value is not None and "id" in value.keys() and value["id"] not in added_nodes:
                node_id = value.get('id')
                node_label = list(value.labels)[0].upper() if value.labels else "UNKNOWN"
                node_color = legend_mapping.get(node_label, "#000000")
                node_size = 25  # Default size
                node_prop_html = "\n".join(f"{k} : {v}" for k, v in value._properties.items())

                if node_label == "lims".upper() and value._properties.get("Status") == "Failed":
                    node_color = "red"
                if node_label == "ProcessOrder".upper():
                    node_size =  50 # Increase size
                if node_label == "batch".upper():
                    node_size = 35  # Increase size
                if node_label == "asset".upper():
                    node_size = 35  # Increase size
                if node_label == "Attributes".upper() and value._properties.get("Temperature") > 24:
                    node_color = "red"

                net.add_node(node_id, label=value.get('Name'), title=node_prop_html, color = node_color, size=node_size)
                added_nodes.add(node_id)
                node_properties[node_id] = value._properties

                # Track batch connections
                if node_label == "batch".upper():
                    batch_connections[node_id] = []
                elif node_label == "wo".upper():
                    wo_connections[node_id] = []
                elif node_label == "asset".upper():
                    asset_connections[node_id] = []

        for key, value in record.items():
            if value is not None and hasattr(value, 'start_node'):
                if value.start_node["id"] in added_nodes and value.end_node["id"] in added_nodes:
                    net.add_edge(value.start_node["id"], value.end_node["id"], title=value.type)

                    # Track batch to LIMS connections
                    start_label = list(value.start_node.labels)[0].upper() if value.start_node.labels else "UNKNOWN"
                    end_label = list(value.end_node.labels)[0].upper() if value.end_node.labels else "UNKNOWN"
                    if start_label == "batch".upper() and end_label == "LIMS":
                        batch_connections[value.start_node["id"]].append(value.end_node["id"])
                    elif start_label == "LIMS" and end_label == "batch".upper():
                        batch_connections[value.end_node["id"]].append(value.start_node["id"])

                    # Track WO connections
                    if start_label == "wo".upper() and end_label == "asset".upper():
                        wo_connections[value.start_node["id"]].append(value.end_node["id"])
                    elif start_label == "asset".upper() and end_label == "wo".upper():
                        wo_connections[value.end_node["id"]].append(value.start_node["id"])

                    # Track asset to OEE connections
                    if start_label == "asset".upper() and end_label == "Attributes".upper():
                        asset_connections[value.start_node["id"]].append(value.end_node["id"])
                    elif start_label == "Attributes".upper() and end_label == "asset".upper():
                        asset_connections[value.end_node["id"]].append(value.start_node["id"])

    #Update batch nodes color if any connected LIMS node failed
    failed_batches = set()
    for batch_id, lims_ids in batch_connections.items():
        for lims_id in lims_ids:
            if node_properties[lims_id].get("Status") == "Failed":
                net.get_node(batch_id)["color"] = "red"
                failed_batches.add(batch_id)
                break
    #Update asset nodes color if any connected OEE node has OEE < 70
    for asset_id, machine_ids in asset_connections.items():
        for id in machine_ids:
            if node_properties[id].get("Temperature") > 24:
                net.get_node(asset_id)["color"] = "red"
                break
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
    <button id="legend-toggle">Node Info</button>
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
    components.html(updated_html, height=1400, width=1200)

def visualize_graph(query):
    """
    Visualize the graph using PyVis.
    """
    with driver.session() as session:
        data = get_graph_data(query,session)  # Fetch all records at once
        with st.spinner("Converting into Graph ..."):
            graph, node_properties = generate_nodes_edges(data)
            save_graph_file(graph, html_file_path)
    driver.close()

def visualize_table(query):
    """
    Visualize the the data as Table.
    """
    with driver.session() as session:
        with st.spinner("Executing query..."):
            with st.spinner("Data Loading ...."):
                graphData = get_graph_data(query,session)
                keys = graphData.keys()
        with st.spinner("Converting into RESULT ..."):
            df = pd.DataFrame(graphData, columns=keys)
            st.table(df)
    driver.close()
    
def app():
    footer()
    st.title("Batch and Asset Genealogy")
    st.sidebar.image(tredence_logo, caption='', width=300)

    data = get_asset_data()
    st.sidebar.subheader("Quick Stats")
    st.sidebar.info(f"Total Batches: {len(data['batch_ids'])}")
    st.sidebar.info(f"Total Assets: {len(data['asset_ids'])}")
    st.sidebar.info(f"Total Process Orders: {len(data['po_ids'])}")

    option = st.sidebar.radio("Select View", options_list)

    facility, site, region = st.columns([1,1,1])
    with facility:
        st.info(f"Facilities : {len(data['facility_ids'])}")
    with site:
        st.info(f"Sites : {len(data['site_ids'])}")
    with region:
        st.info(f"Region : {len(data['region_ids'])}")
    col1, col2, col3, col4, col5, col6, col7 = st.columns([1,1,1,1,1,1,1])

    if option == options_list[0]:
        with col1:
            st.success(f"Batchs:{len(data['batch_ids'])}")
        with col2:
            st.info(f"PO : {len(data['po_ids'])}")
        with col3:
            st.info(f"Product:{len(data['product_ids'])}")
        with col4:
            st.info(f"Material:{len(data['material_ids'])}")
        with col5:
            st.info(f"Supplier:{len(data['supplier_ids'])}")
        with col6:
            st.success(f"Assets:{len(data['asset_ids'])}")
        with col7:
            st.info(f"WO : {len(data['wo_ids'])}")
        st.subheader(option)
        tab1, tab2, tab3 = st.tabs(["UI Tracking","Saved Question", "GEN AI"])
        with tab1:
            st.header("Visualize all batches and assets executed for a Process Order (PO)")
            selected_PO = st.selectbox("Select PO ", data['po_ids'])
            if st.button("Query Knowledge Graph"):
                with st.spinner("Executing query..."):
                    try:
                        with st.spinner("Data Loading ...."):
                            query = f"""
                            MATCH (b:Batch)<-[MA:MANUFACTURES]-(po:ProcessOrder)
                            MATCH (b)-[YI:YIELDS]->(p:Product)
                            MATCH (p)-[FW:FORMULATED_WITH]->(r:Recipe)
                            MATCH (r)-[UM:USES_MATERIAL]->(m:Materials)
                            MATCH (m)-[SB:SUPPLIED_BY]->(sup:Supplier)
                            MATCH (m)-[SI:STORED_IN]->(pm:PlantMaterial)
                            MATCH (pm)-[AA:AVAILABLE_AT]->(f:Facility)
                            MATCH (f)-[LS:LOCATED_AT_SITE]->(s:Site)
                            MATCH (s)-[LR:LOCATED_IN_REGION]->(re:Region)
                            MATCH (b)-[EB:EXECUTED_BY]->(wo:WO)
                            MATCH (b)-[AIN:ANALYZED_IN]->(lims:LIMS)
                            MATCH (wo)-[PER:PERFORMED_ON]->(a:Asset)
                            MATCH (a)-[AL:ASSIGNED_TO_LINE]->(l:Line)
                            MATCH (l)-[LF:LOCATED_IN_FACILITY]->(af:Facility)
                            MATCH (a)-[HI:HAS_INFO]->(ai:AssetInfo)
                            MATCH (a)-[HM:HAS_METADATA]->(ao:Operation)
                            MATCH (a)-[ATTR:HAS_ATTRIBUTE]->(am:Attributes)
                            MATCH (a)-[HO:HAS_OEE]->(oee:OEE)
                            MATCH (a)-[PBO:PROVIDED_BY_OEM]->(oem:OEM)
                            WHERE po.id = "{selected_PO}"
                            RETURN *
                            """
                            visualize_graph(query)
                    except Exception as e:
                        st.error(f"Error executing query: {e}")
        with tab2:
            st.header("Query the failed batches and its root cause?")
            try:
                if st.button("Query Graph"):
                    query = f"""
                    MATCH (b:Batch)<-[MA:MANUFACTURES]-(po:ProcessOrder)
                    MATCH (b)-[YI:YIELDS]->(p:Product)
                    MATCH (p)-[FW:FORMULATED_WITH]->(r:Recipe)
                    MATCH (r)-[UM:USES_MATERIAL]->(m:Materials)
                    MATCH (m)-[SB:SUPPLIED_BY]->(sup:Supplier)
                    MATCH (m)-[SI:STORED_IN]->(pm:PlantMaterial)
                    MATCH (pm)-[AA:AVAILABLE_AT]->(f:Facility)
                    MATCH (f)-[LS:LOCATED_AT_SITE]->(s:Site)
                    MATCH (s)-[LR:LOCATED_IN_REGION]->(re:Region)
                    MATCH (b)-[EB:EXECUTED_BY]->(wo:WO)
                    MATCH (b)-[AIN:ANALYZED_IN]->(lims:LIMS)
                    MATCH (wo)-[PER:PERFORMED_ON]->(a:Asset)
                    MATCH (a)-[AL:ASSIGNED_TO_LINE]->(l:Line)
                    OPTIONAL MATCH (l)-[LF:LOCATED_IN_FACILITY]->(f)
                    MATCH (a)-[HI:HAS_INFO]->(ai:AssetInfo)
                    MATCH (a)-[HM:HAS_METADATA]->(ao:Operation)
                    MATCH (a)-[ATTR:HAS_ATTRIBUTE]->(am:Attributes)
                    MATCH (a)-[HO:HAS_OEE]->(oee:OEE)
                    MATCH (a)-[PBO:PROVIDED_BY_OEM]->(oem:OEM)
                    WHERE lims.Status = "Failed" and am.Temperature >24
                    RETURN *
                    """
                    visualize_graph(query)
                selected_PO = st.selectbox("Select Process order ", data['po_ids'])
                if st.button("TABLE"):
                    query = f"""
                    MATCH (b:Batch)<-[MA:MANUFACTURES]-(po:ProcessOrder)
                    MATCH (b)-[EB:EXECUTED_BY]->(wo:WO)
                    MATCH (wo)-[PER:PERFORMED_ON]->(a:Asset)
                    MATCH (b)-[AIN:ANALYZED_IN]->(lims:LIMS)
                    MATCH (a)-[AL:ASSIGNED_TO_LINE]->(l:Line)
                    MATCH (l)-[LF:LOCATED_IN_FACILITY]->(f:Facility)
                    MATCH (f)-[LS:LOCATED_AT_SITE]->(s:Site)
                    MATCH (s)-[LR:LOCATED_IN_REGION]->(re:Region)
                    MATCH (a)-[ATTR:HAS_ATTRIBUTE]->(am:Attributes)
                    WHERE po.id = "{selected_PO}" AND lims.Status = "Failed" AND am.Temperature > 24
                    RETURN po.id AS PO_ID, 
                        b.id AS Batch_ID, 
                        a.id AS Asset_ID,
                        a.Name AS Asset_Name, 
                        lims.Status AS Lims_Status,
                        am.Temperature AS Machine_Temperature, 
                        l.id AS Line_ID, 
                        f.id AS Facility_ID, 
                        s.Name AS Site, 
                        re.Name AS Region
                    """
                    visualize_table(query)
            except Exception as e:
                st.error(f"Error executing query: {e}")
        #GEN AI
        with tab3:
            st.image(chatgpt_icon, width=50)
            ai_search = st.text_input("AI CHATBOT", "")
            if st.button("RUN"):
                try:
                    batches = re.findall(r'batch(?:es|s)?', ai_search, flags=re.IGNORECASE)
                    # pid = re.findall(r'PO\d+', ai_search, flags=re.IGNORECASE)[0]
                    # all = re.findall(r'all?', ai_search, flags=re.IGNORECASE)
                    failed = re.findall(r'fail?', ai_search, flags=re.IGNORECASE)
                    asset = re.findall(r'asset(?:es|s)?', ai_search, flags=re.IGNORECASE)
                    if batches:
                        if failed:
                            query = f"""
                            MATCH (b:Batch)<-[MA:MANUFACTURES]-(po:ProcessOrder)
                            MATCH (b)-[EB:EXECUTED_BY]->(wo:WO)
                            MATCH (wo)-[PER:PERFORMED_ON]->(a:Asset)
                            MATCH (b)-[AIN:ANALYZED_IN]->(lims:LIMS)
                            MATCH (a)-[ATTR:HAS_ATTRIBUTE]->(am:Attributes)
                            WHERE lims.Status = "Failed" AND am.Temperature > 24
                            RETURN DISTINCT b.id AS Batch_ID
                            """
                            visualize_table(query)
                    elif asset:
                        bid = re.findall(r'BPO\d+-\d+-\d+', ai_search, flags=re.IGNORECASE)[0]
                        if bid:
                            st.text(bid)
                        else:
                            bid = st.text("batch id not available in the database")
                        try:
                            query = f"""
                            MATCH (b:Batch)-[EB:EXECUTED_BY]->(wo:WO)
                            MATCH (wo)-[PER:PERFORMED_ON]->(a:Asset)
                            MATCH (a)-[ATTR:HAS_ATTRIBUTE]->(machine:Attributes)
                            MATCH (a)-[HM:HAS_METADATA]->(op:Operation)
                            MATCH (a)-[HO:HAS_OEE]->(oee:OEE)
                            MATCH (a)-[PBO:PROVIDED_BY_OEM]->(oem:OEM)
                            WHERE b.id = "{bid}"
                            RETURN *
                            """
                            visualize_graph(query)
                        except Exception as e:
                            st.error(f"Error executing query: {e}")
                    else:
                        st.error("Please Try Again")
                except Exception as e:
    
                    st.error(f"Error executing query: {e}")
    #Asset Traceability
    elif option == options_list[2]:
        with col1:
            st.success(f"Total Assets: {len(data['asset_ids'])}")
        with col2:
            st.info(f"Total WO : {len(data['wo_ids'])}")
        st.subheader(option)
        query_type = st.selectbox("Select Questions? ", asset_questions)
        #Asset Monitoring
        if query_type == asset_questions[0]:
            selected_asset = st.selectbox("Select Asset", data['asset_ids'])
            query = f"""
            MATCH (a:Asset {{id: '{selected_asset}'}})-[AL:ASSIGNED_TO_LINE]->(l:Line)
            MATCH (l)-[LF:LOCATED_IN_FACILITY]->(f:Facility)
            MATCH (f)-[FS:LOCATED_AT_SITE]->(s:Site)
            MATCH (s)-[SR:LOCATED_IN_REGION]->(r:Region)
            MATCH (a)-[HI:HAS_INFO]->(ai:AssetInfo)
            MATCH (a)-[HM:HAS_METADATA]->(ao:Operation)
            MATCH (a)-[ATTR:HAS_ATTRIBUTE]->(am:Attributes)
            MATCH (a)-[HO:HAS_OEE]->(oee:OEE)
            MATCH (a)-[PBO:PROVIDED_BY_OEM]->(oem:OEM)
            OPTIONAL MATCH (a)-[PER:PERFORMED_ON]->(wo:WO)
            OPTIONAL MATCH (a)-[ENSURES_COMPLIANCE]->(com:Compliance)
            OPTIONAL MATCH (a)-[REQUIRES_MAINTENANCE]->(main:Maintenance)
            OPTIONAL MATCH (a)-[REQUIRES_CALIBRATION]->(cal:Calibration)
            RETURN *
            """
        #AMC < 2years
        elif query_type == asset_questions[1]:
            query = f"""
            MATCH (a:Asset)-[AL:ASSIGNED_TO_LINE]->(l:Line)
            MATCH (l)-[LF:LOCATED_IN_FACILITY]->(f:Facility)
            MATCH (f)-[FS:LOCATED_AT_SITE]->(s:Site)
            MATCH (s)-[SR:LOCATED_IN_REGION]->(r:Region)
            MATCH (a)-[HI:HAS_INFO]->(ai:AssetInfo)
            MATCH (a)-[HM:HAS_METADATA]->(ao:Operation)
            MATCH (a)-[ATTR:HAS_ATTRIBUTE]->(am:Attributes)
            MATCH (a)-[HO:HAS_OEE]->(oee:OEE)
            MATCH (a)-[PBO:PROVIDED_BY_OEM]->(oem:OEM)
            MATCH (a)-[ENSURES_COMPLIANCE]->(com:Compliance)
            MATCH (a)-[REQUIRES_MAINTENANCE]->(main:Maintenance)
            MATCH (a)-[REQUIRES_CALIBRATION]->(cal:Calibration)
            WHERE ai.HasInsurance = "YES" AND ai.AMCYears < 2
            RETURN *
            """
        #Most utilized assets
        elif query_type == asset_questions[2]:
            query = f"""
            MATCH (a:Asset)<-[:PERFORMED_ON]-(wo:WO)
            WITH a, count(wo) AS TotalWOs
            SET a.TotalWOs = TotalWOs
            RETURN a;
            """
            if st.button("TABLE"):
                query = f"""
                MATCH (a:Asset)<-[PER:PERFORMED_ON]-(wo:WO)
                RETURN a.id AS AssetID, a.Name AS AssetName, count(wo) AS TotalWOs
                ORDER BY TotalWOs DESC
                LIMIT 10;
                """
                visualize_table(query)
        if query_type != asset_questions[2] and st.button("Visualize"):
            try:
                visualize_graph(query)
            except Exception as e:
                st.error(f"Error executing query: {e}")
    #Batch Genealogy
    elif option == options_list[1]:
        with col1:
            st.success(f"Total Batch: {len(data['batch_ids'])}")
        with col2:
            st.info(f"Total PO : {len(data['po_ids'])}")
        with col3:
            st.info(f"Total Product : {len(data['product_ids'])}")
        with col4:
            st.info(f"Total Material : {len(data['material_ids'])}")
        with col5:
            st.info(f"Total Supplier : {len(data['supplier_ids'])}")
        st.subheader(option)
        query_type = st.selectbox("Select Questions? ", batch_questions)
        #Monitor All Batchs
        if query_type == batch_questions[0]:
            # selected_batch = st.selectbox("Select Batch", data['batch_ids'])
            query = f"""
            MATCH (b:Batch)<-[MA:MANUFACTURES]-(po:ProcessOrder)
            MATCH (b)-[YI:YIELDS]->(p:Product)
            MATCH (b)-[AIN:ANALYZED_IN]->(lims:LIMS)
            MATCH (p)-[FW:FORMULATED_WITH]->(r:Recipe)
            MATCH (r)-[UM:USES_MATERIAL]->(m:Materials)
            MATCH (m)-[SB:SUPPLIED_BY]->(sup:Supplier)
            MATCH (m)-[SI:STORED_IN]->(pm:PlantMaterial)
            MATCH (pm)-[AA:AVAILABLE_AT]->(f:Facility)
            MATCH (f)-[LS:LOCATED_AT_SITE]->(s:Site)
            MATCH (s)-[LR:LOCATED_IN_REGION]->(re:Region)
            RETURN *
            """
        #Most Consumed Materials
        elif query_type == batch_questions[1]:
            if st.button("TABLE"):
                limit = st.number_input("Set a Limit", value=10, placeholder="Type a number...")
                query = f"""
                MATCH (m:Materials)<-[UM:USES_MATERIAL]-(r:Recipe)
                MATCH (r)<-[FW:FORMULATED_WITH]-(p:Product)
                MATCH (p)<-[YI:YIELDS]-(b:Batch)
                MATCH (b)<-[MU:MANUFACTURES]-(po:ProcessOrder)
                MATCH (m)-[SB:SUPPLIED_BY]->(sup:Supplier)
                WITH m, SB, sup, count(b) AS TotalBatch
                ORDER BY TotalBatch DESC
                LIMIT {int(limit)}
                RETURN m.id AS MaterialID, sup.id AS SupplierID, m.Location AS Location, TotalBatch, m.Storage AS Storage
                """
                visualize_table(query)
        #PO to Batches
        elif query_type == batch_questions[2]:
            query = f"""
            MATCH (b)<-[MU:MANUFACTURES]-(po:ProcessOrder)
            RETURN *
            """
        #batches have a quality rating below 95%?
        elif query_type == batch_questions[3]:
            query = f"""
            MATCH (b:Batch)<-[MA:MANUFACTURES]-(po:ProcessOrder)
            MATCH (b)-[YI:YIELDS]->(p:Product)
            MATCH (p)-[FW:FORMULATED_WITH]->(r:Recipe)
            MATCH (r)-[UM:USES_MATERIAL]->(m:Materials)
            MATCH (b)-[EB:EXECUTED_BY]->(wo:WO)
            MATCH (b)-[AIN:ANALYZED_IN]->(lims:LIMS)
            WHERE lims.Status = 'Failed'
            Return *
            """
        #Distribution of products to Warehouse
        elif query_type == batch_questions[4]:
            query = f"""
            MATCH (b:Batch)-[WI:WAREHOUSED_IN]->(f:Facility)
            MATCH (b)<-[MA:MANUFACTURES]-(po:ProcessOrder)
            MATCH (b)-[YI:YIELDS]->(p:Product)
            RETURN *
            """
        try:
            if query_type != batch_questions[1] and st.button("Visualize"):
                visualize_graph(query)
        except Exception as e:
            st.error(f"Error executing query: {e}") 
if __name__ == "__main__":
    app()