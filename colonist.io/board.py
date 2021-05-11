from resources import Resources

class Board:
    tiles = None
    vertices = None
    edges = None

    robber_tile = None

    resources = {
        Resources.WOOD: 0,
        Resources.BRICK: 0,
        Resources.WHEAT: 0,
        Resources.SHEEP: 0,
        Resources.ORE: 0
    }
    
    own_settlements = []
    adjacency_map = []
    vertex_tiles = []
    tile_vertices = []

    def __init__(self, board):
        self.tiles = board.tileState.tiles
        self.vertices = board.tileState.tileCorners
        self.edges = board.tileState.tileEdges

        self.buildAdjencyMap()
        self.buildVertexTiles()
        self.buildTileVertices()

    def buildAdjencyMap(self):
        for vertex in self.vertices:
            x = vertex.hexCorner.x
            y = vertex.hexCorner.y
            z = vertex.hexCorner.z 
            
            # TODO: clean up lambda, maybe use a function instead
            data = map(lambda edge_index: { 
                "edge_index": edge_index, 
                "vertex_index": self.getOtherVertexNextToEdge(self.edges[edge_index], vertex) }
                , self.getEdgesNextToVertex(x, y, z))
            self.adjacency_map.append(list(data))

    def buildVertexTiles(self):
        for vertex in self.vertices:
            loc = vertex.hexCorner

            tiles = []

            tiles.append(self.findTileByCoordinates(loc.x, loc.y))
            if loc.z == 0:
                tiles.append(self.findTileByCoordinates(loc.x, loc.y - 1))
                tiles.append(self.findTileByCoordinates(loc.x + 1, loc.y - 1))
            else:
                tiles.append(self.findTileByCoordinates(loc.x - 1, loc.y + 1))
                tiles.append(self.findTileByCoordinates(loc.x, loc.y + 1))

            tiles = [x for x in tiles if x is not None]
                        
            self.vertex_tiles.append(tiles)

    def buildTileVertices(self):
        for tile in self.tiles:
            loc = tile.hexFace

            vertices = []

            vertices.append(self.findVertexIndexByCoordinates(loc.x, loc.y, 0))
            vertices.append(self.findVertexIndexByCoordinates(loc.x, loc.y, 1))
            vertices.append(self.findVertexIndexByCoordinates(loc.x + 1, loc.y - 1, 1))
            vertices.append(self.findVertexIndexByCoordinates(loc.x, loc.y - 1, 1))
            vertices.append(self.findVertexIndexByCoordinates(loc.x, loc.y + 1, 0))
            vertices.append(self.findVertexIndexByCoordinates(loc.x - 1, loc.y + 1, 0))
            
            self.tile_vertices.append(vertices)

    def findTileIndexByCoordinates(self, x, y):
        for i, tile in enumerate(self.tiles):
            if tile.hexFace.x == x and tile.hexFace.y == y:
                return i
        return None

    def findEdgeIndexByCoordinates(self, x, y, z):
        for i, edge in enumerate(self.edges):
            if edge.hexEdge.x == x and edge.hexEdge.y == y and edge.hexEdge.z == z:
                return i
        return None

    def findVertexIndexByCoordinates(self, x, y, z): 
        for i, vertex in enumerate(self.vertices):
            if vertex.hexCorner.x == x and vertex.hexCorner.y == y and vertex.hexCorner.z == z:
                return i
        return None

    # x, y, z: edge coordinates
    # returns 
    def getEdgesNextToVertex(self, x, y, z):
        edges = []
        if z == 0:
            edges.append(self.findEdgeIndexByCoordinates(x, y, 0))
            edges.append(self.findEdgeIndexByCoordinates(x + 1, y - 1, 1))
            edges.append(self.findEdgeIndexByCoordinates(x + 1, y - 1, 2))
        if z == 1:
            edges.append(self.findEdgeIndexByCoordinates(x, y + 1, 0))
            edges.append(self.findEdgeIndexByCoordinates(x, y + 1, 1))
            edges.append(self.findEdgeIndexByCoordinates(x, y, 2))

        edges = [x for x in edges if x is not None] # remove None roads for vertices next to harbor tiles

        return edges

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
        for index in vertices:
            if self.vertices[index] != vertex:
                return index
        return None

    # TODO: Store tiles in a smarter way to make this a O(1) function
    def findTileByCoordinates(self, x, y):
        for tile in self.tiles:
            if tile.hexFace.x == x and tile.hexFace.y == y:
                return tile
        return None
