class Board:
    board_state = None
    adjacency_map = []

    def __init__(self, board):
        self.board_state = board
        self.buildAdjencyMap()

    def buildAdjencyMap(self):
        for vertex in self.board_state.tileState.tileCorners:
            x = vertex.hexCorner.x
            y = vertex.hexCorner.y
            z = vertex.hexCorner.z 
            
            # TODO: clean up lambda, maybe use a function instead
            data = map(lambda edge_index: { "edge": edge_index, "vertex": self.getOtherVertexNextToEdge(self.board_state.tileState.tileEdges[edge_index], vertex) }, self.getEdgesNextToVertex(x, y, z))
            self.adjacency_map.append(list(data))

    def getEdgeIndexByCoordinates(self, x, y, z):
        i = 0
        for edge in self.board_state.tileState.tileEdges:
            if edge.hexEdge.x == x and edge.hexEdge.y == y and edge.hexEdge.z == z:
                return i
            i += 1
        return None

    # x, y, z: edge coordinates
    # returns 
    def getEdgesNextToVertex(self, x, y, z):
        edges = []
        if z == 0:
            edges.append(self.getEdgeIndexByCoordinates(x, y, 0))
            edges.append(self.getEdgeIndexByCoordinates(x + 1, y - 1, 1))
            edges.append(self.getEdgeIndexByCoordinates(x + 1, y - 1, 2))
        if z == 1:
            edges.append(self.getEdgeIndexByCoordinates(x, y + 1, 0))
            edges.append(self.getEdgeIndexByCoordinates(x, y + 1, 1))
            edges.append(self.getEdgeIndexByCoordinates(x, y, 2))

        edges = [x for x in edges if x is not None] # remove None roads for vertices next to harbor tiles

        return edges

    def findVertexIndexByCoordinates(self, x, y, z): 
        for vertex_index, vertex in enumerate(self.board_state.tileState.tileCorners):
            if vertex.hexCorner.x == x and vertex.hexCorner.y == y and vertex.hexCorner.z == z:
                return vertex_index
        return None

    def getVerticesNextToEdge(self, edge):
        x = edge.hexEdge.x
        y = edge.hexEdge.y
        z = edge.hexEdge.z
        vertices = []

        if z == 0:
            vertices.append(self.findVertexIndexByCoordinates(x, y, 0))
            vertices.append(self.findVertexIndexByCoordinates(x, y - 1, 1))
        if z == 1:
            vertices.append(self.findVertexIndexByCoordinates(x, y - 1, 1))
            vertices.append(self.findVertexIndexByCoordinates(x - 1, y + 1, 0))
        if z == 2:
            vertices.append(self.findVertexIndexByCoordinates(x - 1, y + 1, 0))
            vertices.append(self.findVertexIndexByCoordinates(x, y, 1))

        return vertices

    def getOtherVertexNextToEdge(self, edge, vertex):
        vertices = self.getVerticesNextToEdge(edge)
        for v in vertices:
            if self.board_state.tileState.tileCorners[v] != vertex:
                return v
        return None
