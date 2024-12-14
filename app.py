from neo4j import GraphDatabase
from pyvis.network import Network
import dotenv
import os
import streamlit as st
from layout import footer
import streamlit.components.v1 as components
import json
import re
import pandas as pd

uri = st.secrets["NEO4J_URI"]
auth = (st.secrets["NEO4J_USERNAME"], st.secrets["NEO4J_PASSWORD"])
driver = GraphDatabase.driver(uri, auth=auth)

with open('./config.json', 'r') as file:
    config = json.load(file)

options_list = [
    "Manufacturing Knowledge Graph",
    "Batch Genealogy",
    "Assets Traceability",
    # "Ask More Questions-(GEN AI)"
  ]
asset_questions = [
    "Asset Monitoring", 
    "Provide a list of assets with both AMC and insurance coverage of less than 2 years?",
    "Identify the most utilized assets?"
    # "List down assets that has high downtime Percentage (MTBF)",
    # "List down assets that has high Efficiency(OEE)",
    # "List down assets that has low Efficiency(OEE)",
    # "Show asset maintenance summary", 
    # "show asset spare part inventory consumption summary"
    ]
batch_questions = ["Monitor the status and progress of the batch?",
                   "Which materials are being consumed the most in the production process?",
                   "Visualize how Purchase Orders are converted into batches?",
                   "Which batches have a quality rating below 95%?",
                   "How is the distribution of products across different warehouses managed?"]
html_file_path = config["html_file_path"]
network_html_file_path = config["network_html_file_path"]
chatgpt_icon = config["chatgpt_icon"]
tredence_logo = config["tredence_logo"]
legend_mapping = config["legend_mapping"]

def get_neo4j_data(query,session):
    data = session.run(query)
    return data

def get_id_list(node):
    with driver.session() as session:
        results = session.run(f"MATCH (n:{node}) RETURN DISTINCT n.id")
        id_list = sorted([row["n.id"] for row in results])
        return id_list

def get_asset_wo_id():
    with driver.session() as session:
        results = session.run(f"MATCH (a:Asset) -[PER:PERFORMED_ON] -> (WO:WO) return DISTINCT  a.id")
        awo_distinct_id = sorted([row["a.id"] for row in results])
        return awo_distinct_id

@st.cache_data
def get_asset_data():
    with st.spinner("Connecting GraphDB"):
        batch_ids = get_id_list("Batch") 
        asset_ids = get_id_list("Asset")
        facility_ids = get_id_list("Facility") 
        site_ids = get_id_list("Site") 
        region_ids = get_id_list("Region") 
        po_ids = get_id_list("ProcessOrder")
        product_ids = get_id_list("Product")  
        supplier_ids = get_id_list("Supplier")  
        material_ids = get_id_list("Materials")
        wo_ids = get_id_list("WO")
        awo_distinct_id = get_asset_wo_id()
        return batch_ids, asset_ids, facility_ids, site_ids, region_ids,po_ids,product_ids,supplier_ids,material_ids,wo_ids, awo_distinct_id

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
    
def app():
    footer()
    st.title("Batch and Asset Genealogy")
    st.sidebar.image(tredence_logo, caption='', width=300)
    batch_ids, asset_ids, facility_ids, site_ids, region_ids,po_ids,product_ids,supplier_ids,material_ids,wo_ids, awo_distinct_id = get_asset_data()
    facility, site, region = st.columns([1,1,1])
    with facility:
        st.info(f"Facilities : {len(facility_ids)}")
    with site:
        st.info(f"Sites : {len(site_ids)}")
    with region:
        st.info(f"Region : {len(region_ids)}")
    col1, col2, col3, col4, col5, col6, col7 = st.columns([1,1,1,1,1,1,1])
    option = st.sidebar.radio('Select Options', options_list)
    if option == options_list[0]:
        with col1:
            st.success(f"Batchs:{len(batch_ids)}")
        with col2:
            st.info(f"PO : {len(po_ids)}")
        with col3:
            st.info(f"Product:{len(product_ids)}")
        with col4:
            st.info(f"Material:{len(material_ids)}")
        with col5:
            st.info(f"Supplier:{len(supplier_ids)}")
        with col6:
            st.success(f"Assets:{len(asset_ids)}")
        with col7:
            st.info(f"WO : {len(wo_ids)}")
        st.subheader(option)
        tab1, tab2, tab3 = st.tabs(["UI Tracking","Saved Question", "GEN AI"])
        with tab1:
            st.header("Visualize all batches and assets executed for a Process Order (PO)")
            selected_PO = st.selectbox("Select PO ", po_ids)
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
                            MATCH (wo)-[RB:RECORDED_IN]->(lims:LIMS)
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
                            with driver.session() as session:
                                graphData = get_neo4j_data(query,session)
                                with st.spinner("Converting into Graph ..."):
                                    graph, node_properties = generate_nodes_edges(graphData)
                                    save_graph_file(graph, html_file_path)
                            driver.close()
                    except Exception as e:
                        st.error(f"Error executing query: {e}")
        with tab2:
            st.header("Query the failed batches for a selected PO and its root cause?")
            selected_PO = st.selectbox("Select Process order ", po_ids)
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
                    MATCH (wo)-[RB:RECORDED_IN]->(lims:LIMS)
                    MATCH (wo)-[PER:PERFORMED_ON]->(a:Asset)
                    MATCH (a)-[AL:ASSIGNED_TO_LINE]->(l:Line)
                    OPTIONAL MATCH (l)-[LF:LOCATED_IN_FACILITY]->(f:Facility)
                    MATCH (f)-[LS:LOCATED_AT_SITE]->(s:Site)
                    MATCH (s)-[LR:LOCATED_IN_REGION]->(re:Region)
                    MATCH (a)-[HI:HAS_INFO]->(ai:AssetInfo)
                    MATCH (a)-[HM:HAS_METADATA]->(ao:Operation)
                    MATCH (a)-[ATTR:HAS_ATTRIBUTE]->(am:Attributes)
                    MATCH (a)-[HO:HAS_OEE]->(oee:OEE)
                    MATCH (a)-[PBO:PROVIDED_BY_OEM]->(oem:OEM)
                    WHERE po.id = "{selected_PO}" AND lims.Status = "Failed"
                    RETURN *
                    """
                    with driver.session() as session:
                        with st.spinner("Executing query..."):
                            with st.spinner("Data Loading ...."):
                                graphData = get_neo4j_data(query,session)
                        with st.spinner("Converting into Graph ..."):
                            graph, node_properties = generate_nodes_edges(graphData)
                            save_graph_file(graph, html_file_path)
                if st.button("TABLE"):
                    query = f"""
                    MATCH (b:Batch)<-[MA:MANUFACTURES]-(po:ProcessOrder)
                    MATCH (b)-[EB:EXECUTED_BY]->(wo:WO)
                    MATCH (wo)-[PER:PERFORMED_ON]->(a:Asset)
                    MATCH (wo)-[RB:RECORDED_IN]->(lims:LIMS)
                    MATCH (a)-[AL:ASSIGNED_TO_LINE]->(l:Line)
                    MATCH (l)-[LF:LOCATED_IN_FACILITY]->(f:Facility)
                    MATCH (f)-[LS:LOCATED_AT_SITE]->(s:Site)
                    MATCH (s)-[LR:LOCATED_IN_REGION]->(re:Region)
                    MATCH (a)-[ATTR:HAS_ATTRIBUTE]->(am:Attributes)
                    WHERE lims.Status = "Failed" AND am.Temperature > 24
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
                    with driver.session() as session:
                        with st.spinner("Executing query..."):
                            with st.spinner("Data Loading ...."):
                                graphData = get_neo4j_data(query,session)
                                keys = graphData.keys()
                        with st.spinner("Converting into RESULT ..."):
                            df = pd.DataFrame(graphData, columns=keys)
                            st.table(df)
                driver.close()
            except Exception as e:
                st.error(f"Error executing query: {e}")
        with tab3:
            st.image(chatgpt_icon, width=50)
            ai_search = st.text_input("AI CHATBOT", "")
            if st.button("RUN"):
                try:
                    batches = re.findall(r'batch(?:es|s)?', ai_search, flags=re.IGNORECASE)
                    pid = re.findall(r'PO\d+', ai_search, flags=re.IGNORECASE)[0]
                    all = re.findall(r'all?', ai_search, flags=re.IGNORECASE)
                    failed = re.findall(r'fail?', ai_search, flags=re.IGNORECASE)
                    asset = re.findall(r'asset(?:es|s)?', ai_search, flags=re.IGNORECASE)
                    if batches:
                        if failed:
                            query = f"""
                            MATCH (b:Batch)<-[MA:MANUFACTURES]-(po:ProcessOrder)
                            MATCH (b)-[EB:EXECUTED_BY]->(wo:WO)
                            MATCH (wo)-[PER:PERFORMED_ON]->(a:Asset)
                            MATCH (wo)-[RB:RECORDED_IN]->(lims:LIMS)
                            MATCH (a)-[ATTR:HAS_ATTRIBUTE]->(am:Attributes)
                            WHERE lims.Status = "Failed" AND am.Temperature > 24
                            RETURN DISTINCT b.id AS Batch_ID
                            """
                        with driver.session() as session:
                            with st.spinner("Executing query..."):
                                graphData = get_neo4j_data(query,session)
                                keys = graphData.keys()
                            with st.spinner("Converting into RESULT ..."):
                                df = pd.DataFrame(graphData, columns=keys)
                                st.table(df)
                        driver.close()
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
                            with driver.session() as session:
                                with st.spinner("Executing query..."):
                                    with st.spinner("Data Loading ...."):
                                        graphData = get_neo4j_data(query,session)
                                    with st.spinner("Converting into Graph ..."):
                                        graph, node_properties = generate_nodes_edges(graphData)
                                        save_graph_file(graph, html_file_path)
                            driver.close()
                        except Exception as e:
                            st.error(f"Error executing query: {e}")
                    else:
                        st.error("Please Try Again")
                except Exception as e:
                    st.error(f"Error executing query: {e}")
    elif option == options_list[2]:
        with col1:
            st.success(f"Total Assets: {len(asset_ids)}")
        with col2:
            st.info(f"Total WO : {len(wo_ids)}")
        st.subheader(option)
        query_type = st.selectbox("Select Questions? ", asset_questions)
        if query_type == asset_questions[0]:
            selected_asset = st.selectbox("Select Asset", asset_ids)
            query = f"""
            MATCH (a:asset {{id: '{selected_asset}'}})-[al:assetline]->(l:line)
            MATCH (l)-[lf:lineFacility]->(f:facility)
            MATCH (f)-[fs:facilitySite]->(s:site)
            MATCH (s)-[sr:siteRegion]->(r:region)
            MATCH (a)<-[ainfo:assetInfo]-(ai:asset_info)
            MATCH (a)<-[aoper:assetOper]-(ao:operation_data)
            MATCH (a)<-[amachine:assetMachine]-(am:machine_data)
            MATCH (a)<-[aoee:assetOee]-(oee:oee)
            MATCH (a)-[aoem:assetOem]->(oem:oem)
            OPTIONAL MATCH (a)-[awo:assetWO]-(wo:wo)
            OPTIONAL MATCH (a)<-[acom:assetCompliance]-(com:compliance)
            OPTIONAL MATCH (a)<-[amain:assetMain]-(main:maintenance)
            OPTIONAL MATCH (a)<-[acal:assetCal]-(cal:calibration)
            RETURN *
            """
        elif query_type == asset_questions[1]:
            query = f"""
            MATCH (a:asset)-[al:assetline]->(l:line)
            MATCH (l)-[lf:lineFacility]->(f:facility)
            MATCH (f)-[fs:facilitySite]->(s:site)
            MATCH (s)-[sr:siteRegion]->(r:region)
            MATCH (a)<-[ainfo:assetInfo]-(ai:asset_info)
            MATCH (a)<-[aoper:assetOper]-(ao:operation_data)
            MATCH (a)<-[amachine:assetMachine]-(am:machine_data)
            MATCH (a)<-[aoee:assetOee]-(oee:oee)
            MATCH (a)-[aoem:assetOem]->(oem:oem)
            MATCH (a)<-[acom:assetCompliance]-(com:compliance)
            MATCH (a)<-[amain:assetMain]-(main:maintenance)
            MATCH (a)<-[acal:assetCal]-(cal:calibration)
            WHERE ai.HasInsurance = "YES" AND ai.AMCYears < 2
            RETURN *
            """
            if st.button("TABLE"):
                query = f"""
                MATCH (a:asset)-[al:assetline]->(l:line)
                MATCH (l)-[lf:lineFacility]->(f:facility)
                MATCH (f)-[fs:facilitySite]->(s:site)
                MATCH (s)-[sr:siteRegion]->(r:region)
                MATCH (a)<-[ainfo:assetInfo]-(ai:asset_info)
                MATCH (a)<-[aoper:assetOper]-(ao:operation_data)
                MATCH (a)<-[amachine:assetMachine]-(am:machine_data)
                MATCH (a)<-[aoee:assetOee]-(oee:oee)
                MATCH (a)-[aoem:assetOem]->(oem:oem)
                MATCH (a)<-[acom:assetCompliance]-(com:compliance)
                MATCH (a)<-[amain:assetMain]-(main:maintenance)
                MATCH (a)<-[acal:assetCal]-(cal:calibration)
                WHERE ai.HasInsurance = "YES" AND ai.AMCYears < 2
                RETURN a.id,a.Name,f.Name,s.Name, ao.Downtime AS downtime
                ORDER BY downtime DESC
                LIMIT 10
                """
                with driver.session() as session:
                    with st.spinner("Executing query..."):
                        with st.spinner("Data Loading ...."):
                            graphData = get_neo4j_data(query,session)
                            keys = graphData.keys()
                    with st.spinner("Converting into RESULT ..."):
                        df = pd.DataFrame(graphData, columns=keys)
                        st.table(df)
                driver.close()
        elif query_type == asset_questions[2]:
            query = f"""
            MATCH (a:asset)-[:assetWO]->(wo:wo)
            RETURN a, count(wo) AS operationCount
            ORDER BY operationCount DESC
            LIMIT 10;
            """
            if st.button("TABLE"):
                query = f"""
                MATCH (a:asset)-[:assetWO]->(wo:wo)
                RETURN a.id, a.Name, count(wo) AS operationCount
                ORDER BY operationCount DESC
                LIMIT 10;
                """
                with driver.session() as session:
                    with st.spinner("Executing query..."):
                        with st.spinner("Data Loading ...."):
                            graphData = get_neo4j_data(query,session)
                            keys = graphData.keys()
                    with st.spinner("Converting into RESULT ..."):
                        df = pd.DataFrame(graphData, columns=keys)
                        st.table(df)
                driver.close()
        if not query_type == asset_questions[2]:
            if st.button("Visualize"):
                with driver.session() as session:
                    try:
                        with st.spinner("Executing query..."):
                            with st.spinner("Data Loading ...."):
                                graphData = get_neo4j_data(query,session)
                        with st.spinner("Converting into Graph ..."):
                            graph, node_properties = generate_nodes_edges(graphData)
                            save_graph_file(graph, html_file_path)
                        driver.close()
                    except Exception as e:
                        st.error(f"Error executing query: {e}")
    elif option == options_list[1]:
        with col1:
            st.success(f"Total Batch: {len(batch_ids)}")
        with col2:
            st.info(f"Total PO : {len(po_ids)}")
        with col3:
            st.info(f"Total Product : {len(product_ids)}")
        with col4:
            st.info(f"Total Material : {len(material_ids)}")
        with col5:
            st.info(f"Total Supplier : {len(supplier_ids)}")
        st.subheader(option)
        query_type = st.selectbox("Select Questions? ", batch_questions)
        if query_type == batch_questions[0]:
            selected_batch = st.selectbox("Select Batch", batch_ids)
            query = f"""
            MATCH (b:batch)<-[pb:pBatch]-(po:po)
            MATCH (po)<-[ppo:productPo]-(p:product)
            MATCH (p)<-[rp:recipeProduct]-(r:recipe)
            MATCH (r)<-[mr:materialRecipe]-(m:material)
            MATCH (m)<-[supm:supplierMaterial]-(sup:supplier)
            MATCH (m)<-[pmmm:pmMaterial]-(pm:plant_material)
            MATCH (pm)<-[fpm:facilityPm]-(f:facility)
            MATCH (f)-[fs:facilitySite]->(s:site)
            MATCH (s)-[sr:siteRegion]->(re:region)
            MATCH (b)-[blims:batchLims]->(lims:lims)
            WHERE b.id = "{selected_batch}"
            RETURN *
            """
        elif query_type == batch_questions[1]:
            limit = st.number_input("Set a Limit", value=10, placeholder="Type a number...")
            query = f"""
            MATCH (m:material)-[rm:materialRecipe]->(r:recipe)
            MATCH (r)-[pr:recipeProduct]->(p:product)
            MATCH (p)-[ppo:productPo]->(po:po)
            MATCH (po)-[bpo:pBatch]->(b:batch)
            MATCH (m)<-[sm:supplierMaterial]-(sup:supplier)
            WITH m, sm, sup, count(b) as totalbatch
            ORDER BY totalbatch DESC
            limit {int(limit)}
            RETURN m,sm,sup
            """
            if st.button("TABLE"):
                query = f"""
                MATCH (m:material)-[rm:materialRecipe]->(r:recipe)
                MATCH (r)-[pr:recipeProduct]->(p:product)
                MATCH (p)-[ppo:productPo]->(po:po)
                MATCH (po)-[bpo:pBatch]->(b:batch)
                MATCH (m) <-[sm:supplierMaterial]-(sup:supplier)
                WITH m, sup, COUNT(DISTINCT b) as totalBatchCount, COUNT(DISTINCT p) as totalProductCount
                ORDER BY totalBatchCount DESC
                limit 10
                RETURN m.id, sup.id, sup.Name, sup.Address, totalBatchCount, totalProductCount
                """
                with driver.session() as session:
                    with st.spinner("Executing query..."):
                        with st.spinner("Data Loading ...."):
                            graphData = get_neo4j_data(query,session)
                            keys = graphData.keys()
                    with st.spinner("Converting into RESULT ..."):
                        df = pd.DataFrame(graphData, columns=keys)
                        st.table(df)
                driver.close()
        elif query_type == batch_questions[2]:
            query = f"""
            MATCH (b:batch)<-[pob:pBatch]-(po:po)
            RETURN *
            """
            if st.button("TABLE"):
                query = f"""
                MATCH (b:batch)<-[pob:pBatch]-(po:po)
                RETURN po.id, po.Qty, po.Status, count(b) AS batchcount
                """
                with driver.session() as session:
                    with st.spinner("Executing query..."):
                        with st.spinner("Data Loading ...."):
                            graphData = get_neo4j_data(query,session)
                            keys = graphData.keys()
                    with st.spinner("Converting into RESULT ..."):
                        df = pd.DataFrame(graphData, columns=keys)
                        st.table(df)
                driver.close()
        elif query_type == batch_questions[3]:
            query = f"""
            MATCH (b:batch)<-[pb:pBatch]-(po:po)
            MATCH (po)<-[ppo:productPo]-(p:product)
            MATCH (p)<-[rp:recipeProduct]-(r:recipe)
            MATCH (r)<-[mr:materialRecipe]-(m:material)
            MATCH (b)-[blims:batchLims]->(lims:lims)
            MATCH (lims)-[limswo:limsWO]-(wo:wo)
            WHERE lims.Status = 'Failed'
            RETURN *
            """
            if st.button("TABLE"):
                query = f"""
                MATCH (b:batch)<-[pb:pBatch]-(po:po)
                MATCH (po)<-[ppo:productPo]-(p:product)
                MATCH (p)<-[rp:recipeProduct]-(r:recipe)
                MATCH (r)<-[mr:materialRecipe]-(m:material)
                MATCH (b)-[blims:batchLims]->(lims:lims)
                MATCH (lims)-[limswo:limsWO]-(wo:wo)
                WHERE lims.Status = 'Failed'
                RETURN b.id, po.id, p.id, p.Name, wo.id, lims.Test, lims.Result, lims.Status
                """
                with driver.session() as session:
                    with st.spinner("Executing query..."):
                        with st.spinner("Data Loading ...."):
                            graphData = get_neo4j_data(query,session)
                            keys = graphData.keys()
                    with st.spinner("Converting into RESULT ..."):
                        df = pd.DataFrame(graphData, columns=keys)
                        st.table(df)
                driver.close()
        elif query_type == batch_questions[4]:
            query = f"""
            MATCH (b:batch)-[bf:batchWarehouse]->(f:facility)
            RETURN *
            """
            if st.button("TABLE"):
                query = f"""
                MATCH (b:batch)-[bf:batchWarehouse]->(f:facility)
                WITH f, COUNT(b) AS TotalBatches
                ORDER BY TotalBatches DESC
                RETURN f.id, f.SiteID, f.RegionID, f.FType, TotalBatches
                """
                with driver.session() as session:
                    with st.spinner("Executing query..."):
                        with st.spinner("Data Loading ...."):
                            graphData = get_neo4j_data(query,session)
                            keys = graphData.keys()
                    with st.spinner("Converting into RESULT ..."):
                        df = pd.DataFrame(graphData, columns=keys)
                        st.table(df)
                driver.close()
        try:
            if st.button("Visualize"):
                with driver.session() as session:
                    with st.spinner("Executing query..."):
                        with st.spinner("Data Loading ...."):
                            graphData = get_neo4j_data(query,session)
                    with st.spinner("Converting into Graph ..."):
                        graph, node_properties = generate_nodes_edges(graphData)
                        save_graph_file(graph, html_file_path)
                driver.close()
        except Exception as e:
            st.error(f"Error executing query: {e}")
    # elif option == options_list[3]:
    #     st.image(chatgpt_icon, width=50)
    #     ai_search = st.text_input("AI CHATBOT", "")
    #     if st.button("RUN"):
    #         try:
    #             oee = re.findall(r'OEE?', ai_search, flags=re.IGNORECASE)
    #             high = re.findall(r'high?', ai_search, flags=re.IGNORECASE)
    #             low = re.findall(r'low?', ai_search, flags=re.IGNORECASE)
    #             asset = re.findall(r'asset(?:es|s)?', ai_search, flags=re.IGNORECASE)
    #             if oee:
    #                 if high:
    #                     query = f"""
    #                     MATCH (a:asset)<-[aoee:assetOee]-(oee:oee)
    #                     RETURN a.id, oee.OEE
    #                     ORDER BY oee.OEE DESC
    #                     LIMIT 10
    #                     """
    #                 elif low:
    #                     query = f"""
    #                     MATCH (a:asset)<-[aoee:assetOee]-(oee:oee)
    #                     RETURN a.id, oee.OEE
    #                     ORDER BY oee.OEE ASC
    #                     LIMIT 10
    #                     """
    #                 else:
    #                     query = f"""
    #                     MATCH (a:asset)<-[aoee:assetOee]-(oee:oee)
    #                     RETURN a.id, a.Name, oee.OEE
    #                     ORDER BY oee.OEE DESC
    #                     LIMIT 10
    #                     """
    #                 with driver.session() as session:
    #                     with st.spinner("Executing query..."):
    #                         graphData = get_neo4j_data(query,session)
    #                         keys = graphData.keys()
    #                     with st.spinner("Converting into RESULT ..."):
    #                         df = pd.DataFrame(graphData, columns=keys)
    #                         st.table(df)
    #                 driver.close()
    #             elif asset:
    #                 asset_id = re.findall(r'A\d+', ai_search)[0]
    #                 try:
    #                     query = f"""
    #                     MATCH (a:asset {{id: '{asset_id}'}})<-[amachine:assetMachine]-(machine:machine_data)
    #                     MATCH (a)<-[aoper:assetOper]-(od:operation_data)
    #                     MATCH (a)<-[aoee:assetOee]-(oee:oee)
    #                     MATCH (a)-[aoem:assetOem]->(oem:oem)
    #                     RETURN *
    #                     """
    #                     with driver.session() as session:
    #                         with st.spinner("Executing query..."):
    #                             with st.spinner("Data Loading ...."):
    #                                 graphData = get_neo4j_data(query,session)
    #                             with st.spinner("Converting into Graph ..."):
    #                                 graph, node_properties = generate_nodes_edges(graphData)
    #                                 save_graph_file(graph, html_file_path)
    #                     driver.close()
    #                 except Exception as e:
    #                     st.error(f"Error executing query: {e}")
    #             else:
    #                 st.error("Please Try Again")
    #         except Exception as e:
    #             st.error(f"Error executing query: {e}")
if __name__ == "__main__":
    app()